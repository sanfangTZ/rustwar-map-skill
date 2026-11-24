#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_country.py —— 凭空画国家（V4.1 实测版）：真实国界/行政区划矢量打底 +
程序化 RW 风格创作。

数据源（公益 API，无需 key）：
  geoBoundaries gbOpen   https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM}/
  · 返回 JSON 含 gjDownloadURL（GitHub LFS，raw 链接会拿到指针，脚本已自动
    改写为 media.githubusercontent.com 直链）；简化版可用 API 里
    simplifiedGeometryGeoJSON（存在时优先，体积小、栅格化快）。
  · 许可 CC BY 4.0，可随 skill 分发缓存。

流程（国名 → RW 地图）：
  1. 拉 ADM1（一级行政区）GeoJSON → matplotlib.path 栅格化成 200×200
     行政区划掩膜（land=区域 id，水=0）。
  2. 拉真实高程 AWS Terrain Tiles（免 key）→ 按经纬度双线性采样到每格。
  3. 气候底图（纬度带 + 逐行政区拼花 + 海岸沙滩）；
     **真实高程百分位自适应 → STONE/HIGHSTONE 山脉 + 坡度崖壁**（平原国无山、山国满山）。
  4. **D8 汇流分析 → 真实河流走向 → SHOAL 浅水**（可通行 choke point）。
  5. 行政区边界稀疏省道点（不切断连通）。
  6. 首都 + 最远大区府放两队主基地（保证陆地连通），其余大区府放水晶；
     跑 clean/edge_auto_fix ≥98%、装饰用透明底白名单。
  7. 输出 TMX + 标注预览 PNG + 自检报告。

用法：
  python3 gen_country.py JPN 日本
  python3 gen_country.py DEU 德国 --cap 10.4,52.5
"""
import argparse
import json
import math
import os
import random
import sys
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_5v5_common as G
from gen_5v5_common import (GRASS, DIRT, STONE, SAND, MUD, HIGHGRASS,
                            HIGHSTONE, SHOAL, WATER, SEA, OCEAN,
                            TUFT1, TUFT2, TUFT4)

import numpy as np

CACHE = os.path.join(HERE, "data", "geo")
SIZE = G.SIZE
DEM_Z = 7  # AWS Terrain Tiles 缩放级（≈1.2km/px@赤道），可随国家大小自适应下调

API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{adm}/"
DEM_API = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def _lfs_direct(url):
    """geoBoundaries 矢量在 GitHub LFS：raw 域名只会拿到 131B 指针文件，
    必须改写为 media 直链。"""
    return url.replace("https://raw.githubusercontent.com/",
                       "https://media.githubusercontent.com/media/")


def _get_json(url, timeout=120):
    import time
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:                       # 网络抖动重试
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"拉取失败 {url}: {last}")


def fetch_adm(iso, adm="ADM1"):
    """拉并缓存行政区划 GeoJSON（优先简化版）。返回 FeatureCollection dict。"""
    os.makedirs(CACHE, exist_ok=True)
    cache_file = os.path.join(CACHE, f"{iso}_{adm}.geojson")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 10000:
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)
    meta = _get_json(API.format(iso=iso, adm=adm), timeout=30)
    url = meta.get("simplifiedGeometryGeoJSON") or meta.get("gjDownloadURL")
    if not url:
        raise RuntimeError(f"geoBoundaries 未提供 {iso} {adm} 矢量")
    url = _lfs_direct(url)
    gj = _get_json(url)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(gj, f)
    return gj


# ---------- 真实高程 DEM（AWS Terrain Tiles / Mapzen terrarium，CC-BY，免 key）----------

def _tile_xy(lat, lon, z):
    """经纬度 → Web Mercator 瓦片坐标（slippy map 约定）。"""
    n = 2 ** z
    x = (lon + 180) / 360 * n
    latr = math.radians(lat)
    y = (1 - math.log(math.tan(latr) + 1 / math.cos(latr)) / math.pi) / 2 * n
    return x, y


def fetch_dem(lon0, lon1, lat0, lat1, z=DEM_Z):
    """拉取覆盖 bbox 的地形瓦片，拼接成高程图（米，NaN=无数据）。
    返回 (mosaic np.float32, minx_tile, miny_tile, z)。失败/无数据返回 (None,...)"""
    # 自适应降 zoom：瓦片数过多就降一级（大国）
    while True:
        x0 = int(math.floor(_tile_xy(lat0, lon0, z)[0]))
        x1 = int(math.ceil(_tile_xy(lat0, lon1, z)[0])) - 1
        y0 = int(math.floor(min(_tile_xy(lat0, lon0, z)[1], _tile_xy(lat1, lon1, z)[1])))
        y1 = int(math.ceil(max(_tile_xy(lat0, lon0, z)[1], _tile_xy(lat1, lon1, z)[1]))) - 1
        ntx, nty = x1 - x0 + 1, y1 - y0 + 1
        if ntx * nty <= 160 or z <= 4:
            break
        z -= 1
    mosaic = np.full((nty * 256, ntx * 256), np.nan, dtype=np.float32)
    urls = {}
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            urls[(tx, ty)] = DEM_API.format(z=z, x=tx, y=ty)

    def _get(u):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=40).read()
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB")
            a = np.asarray(im).astype(np.float32)
            return (a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256) - 32768.0
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=16) as ex:
        for (tx, ty), arr in zip(urls, ex.map(_get, urls.values())):
            if arr is not None:
                mosaic[(ty - y0) * 256:(ty - y0 + 1) * 256,
                       (tx - x0) * 256:(tx - x0 + 1) * 256] = arr
    if np.isnan(mosaic).all():
        return None, 0, 0, z
    return mosaic, x0, y0, z


def sample_dem(mosaic, minx, miny, z, lat, lon):
    """经纬度 → 双线性采样高程（米）；四角有 NaN 则线性回退，全 NaN 返回 None。"""
    if mosaic is None:
        return None
    n = 2 ** z
    PX = (lon + 180) / 360 * 256 * n
    latr = math.radians(lat)
    PY = (1 - math.log(math.tan(latr) + 1 / math.cos(latr)) / math.pi) / 2 * 256 * n
    gx, gy = PX - minx * 256, PY - miny * 256
    x0, y0 = int(math.floor(gx)), int(math.floor(gy))
    x1, y1 = x0 + 1, y0 + 1
    H, W = mosaic.shape
    if not (0 <= x0 < W - 1 and 0 <= y0 < H - 1):
        return None
    dx, dy = gx - x0, gy - y0
    vs = [mosaic[y0, x0], mosaic[y0, x1], mosaic[y1, x0], mosaic[y1, x1]]
    if any(math.isnan(v) for v in vs):
        cand = [v for v in vs if not math.isnan(v)]
        return float(sum(cand) / len(cand)) if cand else None
    v = (vs[0] * (1 - dx) + vs[1] * dx) * (1 - dy) + (vs[2] * (1 - dx) + vs[3] * dx) * dy
    return float(v)


def build_elev_grid(region, tf, bbox, z=DEM_Z):
    """为 200×200 陆地格逐格采样真实高程（米）；海格返回 None。带缓存。"""
    lon0b, lon1b, lat0b, lat1b = bbox
    cache_file = os.path.join(CACHE, f"dem_{z}_{lon0b:.1f}_{lat0b:.1f}.npz")
    if os.path.exists(cache_file):
        d = np.load(cache_file, allow_pickle=True)
        arr = d["elev"]

        def _clean(v):
            if v is None:
                return None
            try:
                if math.isnan(v):
                    return None
            except (TypeError, ValueError):
                pass
            return float(v)

        return [[_clean(v) for v in row] for row in arr]
    mosaic, mnx, mny, z = fetch_dem(lon0b, lon1b, lat0b, lat1b, z)
    lon0, lat1, kx, scale, ox, oy = tf
    elev = [[None] * SIZE for _ in range(SIZE)]
    if mosaic is not None:
        for r in range(SIZE):
            for c in range(SIZE):
                if not region[r][c]:
                    continue
                lat = lat1 - (r + 0.5 - oy) / scale
                lon = lon0 + (c + 0.5 - ox) / (kx * scale)
                e = sample_dem(mosaic, mnx, mny, z, lat, lon)
                if e is not None:
                    elev[r][c] = e
    np.savez(cache_file, elev=np.array([[ (v if v is not None else np.nan) for v in row] for row in elev], dtype=np.float32))
    return elev


def compute_rivers(elev, region):
    """D8 汇流分析：真实地形决定河流走向。汇流量超阈值的陆地格 → SHOAL 浅水
    （SHOAL 不在 IMPASS，可通行，天然 choke point，不破坏连通）。"""
    H = W = SIZE
    E = np.full((H, W), np.nan)
    for r in range(H):
        for c in range(W):
            if elev[r][c] is not None:
                E[r, c] = elev[r][c]
    dirs = [(-1, 0, 1), (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2)),
            (0, -1, 1), (0, 1, 1), (1, -1, math.sqrt(2)),
            (1, 0, 1), (1, 1, math.sqrt(2))]
    # 降序处理，找每格最陡下坡邻格
    cells = [(r, c) for r in range(H) for c in range(W) if not np.isnan(E[r, c])]
    cells.sort(key=lambda p: E[p[0], p[1]], reverse=True)
    flow = [[-1] * W for _ in range(H)]
    for (r, c) in cells:
        best, bs = -1, -1e-9
        for (dr, dc, d) in dirs:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and not np.isnan(E[rr, cc]):
                sl = (E[r, c] - E[rr, cc]) / d
                if sl > bs:
                    bs, best = sl, rr * W + cc
        flow[r][c] = best
    # 降序累计：上游（更高）先把自己的累加传给下游（更低），下游处理时值已完整
    acc = np.ones((H, W))
    order = sorted(cells, key=lambda p: E[p[0], p[1]], reverse=True)
    for (r, c) in order:
        d = flow[r][c]
        if d >= 0:
            acc.flat[d] += acc[r, c]
    flat = acc[~np.isnan(E)]
    amax = float(flat.max()) if flat.size else 0.0
    thr = max(6.0, 0.08 * amax)      # 主干流级别：汇流量 ≥ 最大盆地的 8%
    rivers = set()
    for r in range(H):
        for c in range(W):
            if np.isnan(E[r, c]):
                continue
            if acc[r, c] >= thr:
                rivers.add((r, c))
    # 总量保护：河流格不超过陆地的 8%，超出就抬阈值
    n_land = flat.size
    while rivers and len(rivers) > 0.08 * n_land:
        thr *= 1.6
        rivers = {(r, c) for (r, c) in rivers if acc[r, c] >= thr}
    return rivers


# ---------- 矢量 → 栅格 ----------

def _polys(geometry):
    """把任意 geometry 拆成 [(outer, [holes...]), ...]。"""
    t = geometry["type"]
    if t == "Polygon":
        return [(geometry["coordinates"][0], geometry["coordinates"][1:])]
    if t == "MultiPolygon":
        return [(p[0], p[1:]) for p in geometry["coordinates"]]
    if t == "GeometryCollection":
        out = []
        for g in geometry.get("geometries", []):
            out += _polys(g)
        return out
    return []


def collect_features(gj):
    """返回 [(region_idx, [poly...], name)]；region_idx 从 1 起。"""
    feats = []
    for i, ft in enumerate(gj["features"], 1):
        props = ft.get("properties", {})
        name = (props.get("shapeName") or props.get("NAME_1")
                or props.get("name") or f"region{i}")
        feats.append((i, _polys(ft["geometry"]), name))
    return feats


def bbox_of(feats):
    """用 2/98 百分位裁剪掉离岛，返回 (lon0, lon1, lat0, lat1)。"""
    xs, ys = [], []
    for _i, polys, _n in feats:
        for outer, _h in polys:
            for x, y in outer:
                xs.append(x); ys.append(y)
    arr = np.array
    lon0 = float(np.percentile(xs, 2)); lon1 = float(np.percentile(xs, 98))
    lat0 = float(np.percentile(ys, 2)); lat1 = float(np.percentile(ys, 98))
    return lon0, lon1, lat0, lat1


def rasterize(feats, margin=8):
    """等积近似（经度 × cos(lat)）拟合到 SIZE×SIZE。返回:
    region 2D(list, 0=水), transform 参数。"""
    lons, lats = [], []
    for _i, polys, _n in feats:
        for outer, _h in polys:
            for x, y in outer:
                lons.append(x); lats.append(y)
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    mlat = (lat0 + lat1) / 2
    kx = math.cos(math.radians(mlat))
    span_x = (lon1 - lon0) * kx
    span_y = lat1 - lat0
    scale = (SIZE - 2 * margin) / max(span_x, span_y, 1e-9)
    ox = (SIZE - span_x * scale) / 2
    oy = (SIZE - span_y * scale) / 2

    def to_px(pts):
        return [((x - lon0) * kx * scale + ox, (lat1 - y) * scale + oy)
                for x, y in pts]

    from matplotlib.path import Path
    ys, xs = np.mgrid[0:SIZE, 0:SIZE]
    pts = np.column_stack([xs.ravel() + 0.5, ys.ravel() + 0.5])
    region = [[0] * SIZE for _ in range(SIZE)]
    for idx, polys, _n in feats:
        for outer, holes in polys:
            path = Path(to_px(outer))
            mask = path.contains_points(pts).reshape(SIZE, SIZE)
            for h in holes:
                hp = Path(to_px(h))
                mask &= ~hp.contains_points(pts).reshape(SIZE, SIZE)
            for r in range(SIZE):
                row = region[r]
                mr = mask[r]
                for c in range(SIZE):
                    if mr[c]:
                        row[c] = idx
    return region, (lon0, lat1, kx, scale, ox, oy)


# ---------- 地形 ----------

def climate_terrain(region, rng, mean_lat, elev):
    """纬度带气候（草/土/林/湿底）拼花 + 海岸沙滩 + **真实高程→山脉**。

    · 平原/丘陵地貌由纬度+每行政区『地貌基因』噪声决定（表现区划拼花）；
    · 山脉位置/高度来自真实 DEM 百分位自适应：
        norm = (elev - p50) / (p95 - p50)
        norm>0.5 或 坡度陡 → STONE；norm>1.1 或 坡度极陡 → HIGHSTONE
      这样平原国（荷兰）几乎无山、山国（瑞士）满山，自动适配；
    · 坡度 = 与 8 邻最大高程差 / 距离，归一化到 span，用于刻画崖壁。"""
    H = W = SIZE
    grid = [[OCEAN] * W for _ in range(H)]
    # 高程统计（仅陆地）
    evs = [elev[r][c] for r in range(H) for c in range(W) if elev[r][c] is not None]
    if evs:
        p50 = float(np.percentile(evs, 50))
        span = max(float(np.percentile(evs, 95)) - p50, 1.0)
        t_stone = float(np.percentile(evs, 82))   # 山地占陆地 ~18%
        t_high = float(np.percentile(evs, 95))    # 极端峰 ~5%
    else:
        p50 = 0.0
        span = 1.0
        t_stone = t_high = 1e18
    n_reg = max(max(row) for row in region) if any(any(row) for row in region) else 1
    genes = {}
    for i in range(1, n_reg + 1):
        h = G._hash(i * 7, 13)
        dom = GRASS if h > 0 else DIRT
        wood = 0.12 + 0.22 * rng.random()
        wet = 0.05 + 0.08 * rng.random()
        genes[i] = (dom, wood, wet)
    # 第一遍：海岸 + 平原/丘陵底图
    for r in range(H):
        for c in range(W):
            reg = region[r][c]
            if not reg:
                continue
            coast = any(not (0 <= r + dr < H and 0 <= c + dc < W)
                        or region[r + dr][c + dc] == 0
                        for dr in (-1, 0, 1) for dc in (-1, 0, 1))
            if coast:
                grid[r][c] = SAND
                continue
            dom, wood, wet = genes[reg]
            n = G._fbm(r + reg * 37, c + reg * 73,
                       ((1 / 34.0, 0.55), (1 / 16.0, 0.45)))
            if n > 0.30 - wood:
                grid[r][c] = HIGHGRASS
            elif n < -0.34 + wet:
                grid[r][c] = MUD
            else:
                grid[r][c] = dom
    # 第二遍：真实高程 + 坡度 → 山脉（不覆盖沙滩/湿地）
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if not region[r][c] or grid[r][c] == SAND:
                continue
            e = elev[r][c]
            if e is None:
                continue
            norm = (e - p50) / span
            # 坡度（邻里最大落差 / 距离）
            slope = 0.0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    en = elev[r + dr][c + dc]
                    if en is None:
                        continue
                    d = math.hypot(dr, dc)
                    slope = max(slope, abs(e - en) / d)
            slope_n = slope / span
            if e >= t_high or slope_n > 0.45:
                grid[r][c] = HIGHSTONE        # 仅极端峰/极陡崖不可通行
            elif e >= t_stone or slope_n > 0.20:
                grid[r][c] = STONE            # 普通山地=可通行岩石
    return grid


def ensure_connected(grid, a, b):
    """若两基地被真实山墙(HIGHSTONE)隔断，沿 4 邻接最低代价路把 HIGHSTONE 凿成
    山口(STONE)。采用与 verify_connectivity 一致的 4 邻接判定，且凿出 3 格宽走廊
    （中心格 4 邻同类≥3，不会被后续 clean 当尖刺抹掉）。"""
    import heapq
    H = W = SIZE
    OR = ((1, 0), (-1, 0), (0, 1), (0, -1))
    def passable(r, c):
        return 0 <= r < H and 0 <= c < W and grid[r][c] not in G.IMPASS
    def cost(r, c):
        return 50 if grid[r][c] == HIGHSTONE else 1
    start, goal = a, b
    if not (passable(*start) and passable(*goal)):
        return False
    # 先试普通 4 邻接 BFS（不走任何不可通行地形）是否已连通
    from collections import deque
    seen = {start}; q = deque([start])
    while q:
        r, c = q.popleft()
        if (r, c) == goal:
            return True
        for dr, dc in OR:
            nr, nc = r + dr, c + dc
            if passable(nr, nc) and (nr, nc) not in seen:
                seen.add((nr, nc)); q.append((nr, nc))
    # 不连通 → A* 允许穿 HIGHSTONE（高代价），再把路径上的 HIGHSTONE 凿成 STONE
    g = {start: 0}
    pq = [(0, 0, start)]
    prev = {}
    while pq:
        _f, d, (r, c) = heapq.heappop(pq)
        if (r, c) == goal:
            break
        for dr, dc in OR:
            nr, nc = r + dr, c + dc
            if not passable(nr, nc):
                continue
            nd = d + cost(nr, nc)
            if (nr, nc) not in g or nd < g[(nr, nc)]:
                g[(nr, nc)] = nd
                prev[(nr, nc)] = (r, c)
                heapq.heappush(pq, (nd + math.hypot(nr - goal[0], nc - goal[1]), nd, (nr, nc)))
    if goal not in prev and goal != start:
        return False
    # 凿 3 格宽山口：路径格 + 其 4 邻的 HIGHSTONE → STONE
    cur = goal
    carved = 0
    path = []
    while cur != start:
        path.append(cur)
        cur = prev[cur]
    path.append(start)
    for (r, c) in path:
        for dr, dc in ((0, 0),) + OR:
            rr, cc = r + dr, c + dc
            if passable(rr, cc) and grid[rr][cc] == HIGHSTONE:
                grid[rr][cc] = STONE
                carved += 1
    print(f"      山墙隔断 → 已凿通山口 {carved} 格（STONE 走廊）")
    return True


def _dist_to_coast(region):
    """BFS：每陆格到最近水格的步数。"""
    from collections import deque
    H = W = SIZE
    dist = [[-1] * W for _ in range(H)]
    q = deque()
    for r in range(H):
        for c in range(W):
            if region[r][c] == 0:
                dist[r][c] = 0
                q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and dist[rr][cc] < 0 and region[rr][cc]:
                dist[rr][cc] = dist[r][c] + 1
                q.append((rr, cc))
    return dist


def region_borders(region, grid, rng):
    """行政区界只做『稀疏省道点』（DIRT 虚线，p=0.3），仅刻在草/林地上——
    区划本身靠地貌拼花区分，避免把小区划密布的国家刻成泥巴。"""
    H = W = SIZE
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            reg = region[r][c]
            if not reg or grid[r][c] not in (GRASS, HIGHGRASS):
                continue
            for dr, dc in ((0, 1), (1, 0)):
                nb = region[r + dr][c + dc]
                if nb and nb != reg and rng.random() < 0.3:
                    grid[r][c] = DIRT
                    break


def _final_edge_rate(grid, region):
    """终检修边率（V4.2）：与 V4.1 edge_metrics 口径完全一致，但【豁免河流(SHOAL)
    与真实海岸线】——二者是真实地理要素（细线 / 海岸毛边），不应被算作修边噪声。
    仅考核『陆地地形』干净度，达到 ≥98% 才允许出图。"""
    H = W = SIZE
    iso = cnt0 = diagonly = 0
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            cat = grid[r][c]
            if cat not in (GRASS, DIRT, STONE, SAND, MUD, HIGHGRASS, HIGHSTONE):
                continue                       # 豁免 SHOAL 河流与全部水域
            if cat == SAND and (
                    any(grid[r + dr][c + dc] in (OCEAN, SEA, WATER)
                        for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                        if (dr, dc) != (0, 0))):
                continue                       # 豁免真实海岸沙滩带
            orth = [grid[r + dr][c + dc] for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            diag_nei = [grid[r + dr][c + dc] for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1))]
            cnt = sum(1 for x in orth + diag_nei if x == cat)
            if cnt < 3:
                iso += 1
            if cnt == 0:
                cnt0 += 1
            if cat not in orth and any(x == cat for x in diag_nei):
                diagonly += 1
    interior = max(1, (H - 2) * (W - 2))
    return 100.0 * (1 - (iso + cnt0 + diagonly) / interior), iso, cnt0, diagonly


# ---------- 城市 / 基地 ----------

def region_centers(region, feats):
    """每行政区陆地像元质心（row, col）。"""
    import collections
    acc = collections.defaultdict(lambda: [0, 0, 0])
    for r in range(SIZE):
        for c in range(SIZE):
            reg = region[r][c]
            if reg:
                a = acc[reg]
                a[0] += r; a[1] += c; a[2] += 1
    out = {}
    for reg, (sr, sc, n) in acc.items():
        if n >= 4:
            out[reg] = (int(sr / n), int(sc / n))
    names = {i: n for i, _p, n in feats}
    return out, names


def largest_cc(region):
    """最大陆地连通块（4 连通）set。"""
    from collections import deque
    seen = [[False] * SIZE for _ in range(SIZE)]
    best = set()
    for r in range(SIZE):
        for c in range(SIZE):
            if region[r][c] and not seen[r][c]:
                comp = set()
                q = deque([(r, c)])
                seen[r][c] = True
                while q:
                    rr, cc = q.popleft()
                    comp.add((rr, cc))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < SIZE and 0 <= nc < SIZE and \
                                region[nr][nc] and not seen[nr][nc]:
                            seen[nr][nc] = True
                            q.append((nr, nc))
                if len(comp) > len(best):
                    best = comp
    return best


def largest_passable(grid):
    """最大『地形可通行』连通块（4 连通）set。可通行 = 不在 IMPASS
    （水/高石不可通，SHOAL 浅滩可通）。用于选基地，保证两基地落在同一块能
    互相走到的陆地上。"""
    from collections import deque
    seen = [[False] * SIZE for _ in range(SIZE)]
    best = set()
    for r in range(SIZE):
        for c in range(SIZE):
            if grid[r][c] not in G.IMPASS and not seen[r][c]:
                comp = set()
                q = deque([(r, c)])
                seen[r][c] = True
                while q:
                    rr, cc = q.popleft()
                    comp.add((rr, cc))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < SIZE and 0 <= nc < SIZE and \
                                grid[nr][nc] not in G.IMPASS and not seen[nr][nc]:
                            seen[nr][nc] = True
                            q.append((nr, nc))
                if len(comp) > len(best):
                    best = comp
    return best


def drop_islets(region, min_size=4):
    """海域去碎屑（V4.2 细节美观）：连通面积 < min_size 的迷你岛整块沉海。
    真实大岛（数百格）不受影响；1~3 格的栅格化碎斑看起来像海上芝麻，
    一律清除。返回清除的岛数。"""
    H = W = SIZE
    seen = [[False] * W for _ in range(H)]
    removed = 0
    for r0 in range(H):
        for c0 in range(W):
            if not region[r0][c0] or seen[r0][c0]:
                continue
            comp = [(r0, c0)]
            seen[r0][c0] = True
            q = deque(comp)
            while q:
                r, c = q.popleft()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < H and 0 <= nc < W and region[nr][nc]
                            and not seen[nr][nc]):
                        seen[nr][nc] = True
                        comp.append((nr, nc))
                        q.append((nr, nc))
            if len(comp) < min_size:
                for (r, c) in comp:
                    region[r][c] = 0
                removed += 1
    return removed


def pick_bases(region, grid, capital=None):
    """在『地形可通行』最大连通块上选两队基地，天然地面互达（V4.2 修正：原版用
    行政区掩膜选基，会把行政区相邻、地形却被水隔断的两块误判为连通 → 基地互不
    可达）。轮廓/地形不变，只把基地挪到同一可通行陆块两端。
    · 给首都(row,col) → 队0 落最近可通行格；队1 = BFS 最远点（≈直径端点）
    · 否则任取一点双扫 BFS 求直径两端。"""
    from collections import deque
    comp = largest_passable(grid)
    if not comp:
        raise RuntimeError("没有可通行陆地")

    def bfs(src):
        dist = {src: 0}
        q = deque([src])
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = (r + dr, c + dc)
                if p in comp and p not in dist:
                    dist[p] = dist[(r, c)] + 1
                    q.append(p)
        return dist

    if capital:
        a = min(comp, key=lambda p: math.hypot(p[0] - capital[0], p[1] - capital[1]))
    else:
        a = next(iter(comp))
    da = bfs(a)
    b = max(da, key=lambda p: da[p])
    return a, b


def carve_road(grid, a, b):
    """两地 BFS 不通时刻一条 2 格宽 DIRT 公路（等距折线）。"""
    H = W = SIZE
    (r0, c0), (r1, c1) = a, b
    n = int(max(abs(r1 - r0), abs(c1 - c0)) * 1.5) + 1
    for i in range(n + 1):
        t = i / n
        r = int(round(r0 + (r1 - r0) * t))
        c = int(round(c0 + (c1 - c0) * t + 2.5 * math.sin(t * 5)))   # 微弯更自然
        for rr in (r, min(r + 1, H - 1)):
            for cc in (c, min(c + 1, W - 1)):
                if 0 <= rr < H and 0 <= cc < W:
                    grid[rr][cc] = DIRT


# ---------- 主流程 ----------

def generate(iso, name, capital=None, out=None, seed=42):
    rng = random.Random(seed)
    out = out or os.path.join(HERE, f"rw_country_{iso.lower()}.tmx")
    print(f"[1/6] 拉取 geoBoundaries {iso} ADM1 ...")
    gj = fetch_adm(iso)
    feats = collect_features(gj)
    print(f"      {len(feats)} 个一级行政区")
    print("[2/6] 栅格化 200x200 ...")
    region, tf = rasterize(feats)
    n_drop = drop_islets(region, min_size=4)
    print(f"      海域碎岛清理: 沉掉 {n_drop} 个 <4 格碎斑")
    land = sum(1 for row in region for v in row if v)
    print(f"      陆地 {land} 格 ({land/SIZE/SIZE*100:.0f}%)")
    print("[3/6] 真实高程 DEM + 气候地形 + 山脉 ...")
    lats = []
    for _i, polys, _n in feats:
        for outer, _h in polys:
            for _x, y in outer:
                lats.append(y)
    mlat = sum(lats) / len(lats)
    bbox = bbox_of(feats)
    elev = build_elev_grid(region, tf, bbox)
    evs = [e for row in elev for e in row if e is not None]
    if evs:
        print(f"      真实高程: 最低 {min(evs):.0f}m  中位 {np.median(evs):.0f}m  "
              f"最高 {max(evs):.0f}m")
    else:
        print("      !! 未能获取 DEM，退回无山脉的纯气候地形")
    grid = climate_terrain(region, rng, mlat, elev)
    region_borders(region, grid, rng)
    mt = sum(1 for row in grid for v in row if v in (STONE, HIGHSTONE))
    print(f"      山脉占比: {mt/SIZE/SIZE*100:.1f}%")
    # 真实河流（D8 汇流）先算好，但**在修边之后落笔**，避免被 clean 当成尖刺抹掉
    rivers = compute_rivers(elev, region)
    orig = [row[:] for row in grid]   # ★快照：修边/回注只清噪，不吞海岸地形
    print("[4/6] 修边(≥98%) ...")
    rate, iso_c, cnt0, diag, it = G.edge_auto_fix(grid)
    print(f"      正确率 {rate:.2f}%（{it} 轮）")
    # 真实河流（D8 汇流）→ SHOAL 浅水（可通行 choke point），修边之后落笔
    for (r, c) in rivers:
        if region[r][c] and grid[r][c] != HIGHSTONE:
            grid[r][c] = SHOAL
    # ★河流 4 连通补间（V4.2 细节）：D8 汇流走对角步进，1 格宽 SHOAL 链在
    # 预览里成一节一节的断续方块。对每对对角相邻河格，在其 L 形中间格补一个
    # SHOAL，河流在图上即为连续水线（仍是可通行 choke point）。
    rset = set(rivers)
    for (r, c) in rivers:
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            p = (r + dr, c + dc)
            if p not in rset:
                continue
            for m in ((r + dr, c), (r, c + dc)):
                if (0 <= m[0] < SIZE and 0 <= m[1] < SIZE and region[m[0]][m[1]]
                        and grid[m[0]][m[1]] not in (HIGHSTONE, SHOAL,
                                                     WATER, SEA, OCEAN)):
                    grid[m[0]][m[1]] = SHOAL
                    break
    print(f"      河流/水系格数: {len(rivers)}")
    # 海岸线回注：clean 会把单像素宽的真陆桥/海角当尖刺溶成海。回注时
    # 【恢复修边前原始地形】而非一律 SAND——否则每轮 clean+回注都会把海岸
    # 向内啃一格、全变沙滩（日本全岛差点被沙圈吞掉）。
    for r in range(SIZE):
        for c in range(SIZE):
            if region[r][c] and grid[r][c] in (OCEAN, SEA, WATER):
                ov = orig[r][c]
                grid[r][c] = ov if ov not in (OCEAN, SEA, WATER, SHOAL) else SAND
    # ★终检修边（V4.2 细节）：河流/海岸落笔后，用『原样』clean 再跑一遍，
    # 把回注与河流引入的零散麻点抹平；但【保护河流(SHOAL)与真实海岸线不被误吞】
    # —— 先快照河流格，clean 后还原；再补一次海岸回注（被溶成海的陆桥/海角复原）。
    river_cells = {(r, c) for r in range(SIZE) for c in range(SIZE)
                  if grid[r][c] == SHOAL}
    G.clean_all(grid, iters=2)
    for (r, c) in river_cells:
        if 0 <= r < SIZE and 0 <= c < SIZE:
            grid[r][c] = SHOAL
    for r in range(SIZE):
        for c in range(SIZE):
            if region[r][c] and grid[r][c] in (OCEAN, SEA, WATER):
                ov = orig[r][c]
                grid[r][c] = ov if ov not in (OCEAN, SEA, WATER, SHOAL) else SAND
    # ★近岸浅水带（V4.2 细节美观）：原先海域一水到底全是深蓝 OCEAN，与沙滩
    # 硬切、生硬突兀。现用【多源 BFS 距离场】生成等宽浅水过渡带（8 邻 BFS，
    # 离陆地切比雪夫步数 ≤2 的海格 → WATER），海岸层次 = 沙滩→浅蓝→深蓝。
    # 环带与海岸线平行（等深线效果），无需再平滑——任何"填补/清除"规则都会
    # 把带子撑出方头或啃出断口。
    dist = [[99] * SIZE for _ in range(SIZE)]
    q = deque()
    for r in range(SIZE):
        for c in range(SIZE):
            if region[r][c]:
                dist[r][c] = 0
                q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (0 <= nr < SIZE and 0 <= nc < SIZE
                        and dist[nr][nc] > dist[r][c] + 1):
                    dist[nr][nc] = dist[r][c] + 1
                    q.append((nr, nc))
    for r in range(SIZE):
        for c in range(SIZE):
            if (not region[r][c] and grid[r][c] == OCEAN
                    and dist[r][c] <= 2):
                grid[r][c] = WATER
    # 水内微修（只动水、不碰陆地，避免把带子撑肥）：
    #   · 4 连通 WATER 碎斑（<4 格，海岸 1px 凸角产生的飘出蓝点/细须）→ 沉回 OCEAN；
    #   · 带内单格 OCEAN 孔洞（8 邻 ≥6 格水）→ 补成 WATER。
    # 主带（贴岸 2 格宽）每处都 ≥4 格连通，不受影响；深浅交界由此干净。
    while True:
        seen = [[False] * SIZE for _ in range(SIZE)]
        sink = []
        for r in range(SIZE):
            for c in range(SIZE):
                if grid[r][c] != WATER or seen[r][c]:
                    continue
                comp, q = [], deque([(r, c)])
                seen[r][c] = True
                while q:
                    y, x = q.popleft()
                    comp.append((y, x))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dr, x + dc
                        if (0 <= ny < SIZE and 0 <= nx < SIZE
                                and not seen[ny][nx] and grid[ny][nx] == WATER):
                            seen[ny][nx] = True
                            q.append((ny, nx))
                if len(comp) < 4:
                    sink.extend(comp)
        if not sink:
            break
        for (r, c) in sink:
            grid[r][c] = OCEAN
    holes = []
    for r in range(1, SIZE - 1):
        for c in range(1, SIZE - 1):
            if grid[r][c] != OCEAN:
                continue
            nb = [grid[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                  if (dr, dc) != (0, 0)]
            # 只数 WATER 邻居：带内单格孔洞（≥6 格浅水围着）才补；
            # 深海格 0 个 WATER 邻居，绝不能被误补（V4.2 踩坑：早先写成
            # x in (WATER, OCEAN)，把整片大洋都"补"成了浅水，深浅层次全丢）
            if sum(1 for x in nb if x == WATER) >= 6:
                holes.append((r, c))
    for (r, c) in holes:
        grid[r][c] = WATER
    frate, fiso, fcnt0, fdiag = _final_edge_rate(grid, region)
    print(f"      终检修边率 {frate:.2f}%（iso={fiso} cnt0={fcnt0} diag={fdiag}）")
    if frate < 98.0:
        raise RuntimeError(
            f"终检修边正确率 {frate:.2f}% < 98%（iso={fiso} cnt0={fcnt0} diag={fdiag}）"
            f"—— 拒绝出图，请检查地形生成逻辑")
    print("[5/6] 基地/水晶/装饰 ...")
    centers, names = region_centers(region, feats)
    cap_px = None
    if capital:
        lat, lon = capital
        lon0, lat1, kx, scale, ox, oy = tf
        cap_px = ((lat1 - lat) * scale + oy, (lon - lon0) * kx * scale + ox)
        cap_px = (int(cap_px[0]), int(cap_px[1]))
    base_a, base_b = pick_bases(region, grid, capital=cap_px)
    if capital:
        print(f"      队0 落首都附近 {base_a}，队1 落对角 {base_b}")
    spawns = [(base_a[0], base_a[1], 0), (base_b[0], base_b[1], 1)]
    G.protect_bases(grid, spawns)
    # 真实山墙可能隔断基地 → 凿通山口，保证陆地连通（山口即最终地形，不再 clean）
    ensure_connected(grid, base_a, base_b)
    items = [[0] * SIZE for _ in range(SIZE)]
    G.place_res(items, grid, spawns)
    # 其余大区府放水晶（距两基地都远、可通行）
    crystals = []
    for reg, (r, c) in sorted(centers.items()):
        if len(crystals) >= 8:
            break
        if (r, c) in (base_a, base_b) or grid[r][c] in G.IMPASS:
            continue
        if min(math.hypot(r - base_a[0], c - base_a[1]),
               math.hypot(r - base_b[0], c - base_b[1])) < 12:
            continue
        crystals.append((r, c))
    decor = G.make_decor(grid, rng, opts={
        "density": 1.0,
        "stone_decor": False,                # 山地本身已是石纹，不再撒巨岩石堆
        "sand_tiles": [TUFT1, TUFT4, TUFT2],  # 沙滩只放草簇/小花
        "mud_tiles": [TUFT2, TUFT4],          # 泥地/土径只放草簇/小花
    })
    # 国家图陆地占比低，补一层稀疏乡野点缀——【只放花草树】（V4.1 铁律）：
    # 草地撒草簇/花 + 极稀疏绿松，沙泥地撒草簇；山石地保持净空，杜绝"密密麻麻石块"。
    for r in range(2, SIZE - 2):
        for c in range(2, SIZE - 2):
            if decor[r][c] or grid[r][c] in G.IMPASS:
                continue
            v = grid[r][c]
            if v == GRASS:
                p, pool = 0.04, [G.TUFT1, G.TUFT2, G.TUFT4, G.TUFT3]
                if rng.random() < 0.15:       # 草地上偶尔一棵绿松，打破空旷
                    pool = pool + [G.PINE1, G.PINE2]
            elif v in (SAND, MUD, DIRT):
                p, pool = 0.02, [G.TUFT1, G.TUFT2, G.TUFT4]
            else:
                continue
            if rng.random() < p:
                decor[r][c] = G.GROUND_FG + rng.choice(pool)
    print("[6/6] 写 TMX + 校验 ...")
    intro = f"【{name}】真实行政区划 + 真实高程打底：{len(feats)} 个一级行政区，山脉按真实 DEM 隆起、河流按真实汇流走向。两队分据两端区府，拆光对方主基地获胜。"
    tree, issues = G.write_tmx(grid, decor, items, spawns, crystals, out, intro=intro)
    v = G.verify_connectivity(grid, spawns, [])
    v["edge"] = (fiso, fcnt0, fdiag)
    G.report(grid, items, decor, crystals, spawns, v, issues, f"{name}({iso})")
    if issues:
        print("!! 触发器/结构问题:", issues)
        sys.exit(1)
    # 预览图
    from gen_5v5_preview import render_annotated
    png = os.path.splitext(out)[0] + "_preview.png"
    render_annotated(out, png, f"{name} {iso}", [])
    print("✓ 输出:", out, "&&", png)
    return out, png


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", help="ISO3 国家代码，如 JPN")
    ap.add_argument("name", help="国家中文名，如 日本")
    ap.add_argument("--cap", default=None, help="首都纬度,经度（可选，如 35.7,139.7）")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    cap = tuple(float(x) for x in a.cap.split(",")) if a.cap else None
    generate(a.iso.upper(), a.name, capital=cap, seed=a.seed)
