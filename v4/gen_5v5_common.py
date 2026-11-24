#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 5V5 竞技图 共享框架（无水上搭桥版）

核心思路（相对旧版『中央水道+桥梁』的根本改动）：
- 左右对抗 5V5（奇偶分队：左=偶 0/2/4/6/8，右=奇 1/3/5/7/9）。
- 两侧用『纯陆地』连接：中央是 山体/峡谷（山脊隘口 或 干峡谷地面走廊），
  绝不在中央挖水道再架桥。水只作为两侧湖泊/海岸装饰存在，不做分隔。
- 非对称但平衡：两侧地貌不同（林海 vs 草原、绿洲高原 vs 赤岩峡谷），
  但通道数、到中心路径距离、掩体密度功能对等。
- 空军不能定胜负：中央是起伏林地/山地掩体 + 山脊隘口天然阻碍视线与机动，
  水晶散落于通道与林间需地面占领。
- 量化红线（防绿板/防荒凉/抑空军）：草地最大 4 邻连片 <10%；装饰密度 >3%；
  中央 80×80 最大单一地形 <45%；左右到中心平均路径差异 <15%；≥3 条地面通道；
  地形 ≥9 类且单类 ≤55%。

复用：gen_combined.autotile（四角自动拼接）、gen_koth（图集合并/TMX/校验/渲染）。
"""
import os, math, base64, gzip, struct, random
from collections import deque, Counter
import xml.etree.ElementTree as ET
import numpy as np
import gen_combined as C
import gen_koth as K

HERE = os.path.dirname(os.path.abspath(__file__))
GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

# 地形角索引
GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14
IMPASS = {WATER, SEA, OCEAN, HIGHSTONE}

SIZE = 200
LEFT_X, RIGHT_X = 26, 174
SPAWN_YS = [22, 60, 100, 140, 178]
TEAMS_L = [0, 2, 4, 6, 8]
TEAMS_R = [1, 3, 5, 7, 9]

# 装饰 tile（透明背景道具，来自 地面层整合 图集）
ROCK = 826      # 岩石
WOOD = 934      # 枯木
TREE = 499      # 草中树


# ---------- 确定性噪声（可复现） ----------
def _hash(ix, iy):
    h = (ix * 374761393 + iy * 668265263) & 0x7fffffff
    h = (h ^ (h >> 13)) * 1274126177
    h &= 0x7fffffff
    return (h / 0x7fffffff) * 2 - 1

def _vn(x, y, f):
    gx = x * f; gy = y * f
    ix = int(math.floor(gx)); iy = int(math.floor(gy))
    fx = gx - ix; fy = gy - iy
    ux = fx * fx * (3 - 2 * fx); uy = fy * fy * (3 - 2 * fy)
    n00 = _hash(ix, iy); n10 = _hash(ix + 1, iy)
    n01 = _hash(ix, iy + 1); n11 = _hash(ix + 1, iy + 1)
    return (n00 + (n10 - n00) * ux) + ((n01 + (n11 - n01) * ux) - (n00 + (n10 - n00) * ux)) * uy

def _noise(r, c):
    return 0.55 * _vn(r, c, 1 / 26.0) + 0.30 * _vn(r, c, 1 / 13.0) + 0.15 * _vn(r, c, 1 / 6.0)

def _fbm(r, c, octaves=((1 / 55.0, 0.55), (1 / 27.0, 0.45))):
    return sum(w * _vn(r, c, f) for f, w in octaves)


def blob(grid, cr, cc, rad, cat, rng, lobes=6, jit=0.18, only=None):
    H = len(grid); W = len(grid[0])
    phase = rng.uniform(0, math.tau)
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cr, c - cc)
            ang = math.atan2(r - cr, c - cc)
            rr = rad * (1 + jit * math.sin(lobes * ang + phase))
            if d <= rr:
                if only is not None and grid[r][c] not in only:
                    continue
                grid[r][c] = cat


def ridge(grid, spine_fn, base_half, core, rng, skip=None):
    """连绵山脊（软边有机）：脊线低频缓弯 + 噪声软半宽，核心 HIGHSTONE 外圈 STONE。
    skip: 行集合或 row->bool，跳过（=隘口/鞍部，保持草地可通行）。"""
    H = len(grid); W = len(grid[0])
    for r in range(4, H - 4):
        if skip is not None:
            if isinstance(skip, set):
                if r in skip:
                    continue
            elif skip(r):
                continue
        spine = spine_fn(r)
        hw = base_half + 1.2 * math.sin(r * 0.05) + 2.0 * _vn(r, 3, 1 / 13.0)
        for c in range(int(spine - hw - 2), int(spine + hw + 2) + 1):
            d = abs(c - spine)
            if 0 <= c < W and grid[r][c] not in (WATER, SEA, OCEAN):
                if d <= max(0.5, core + 0.4 * math.sin(r * 0.1)):
                    grid[r][c] = HIGHSTONE
                elif d <= hw:
                    grid[r][c] = STONE


def clean_highstone(grid):
    """把孤立 HIGHSTONE 与 3×3 实心块边缘化，避免突兀悬崖斑。"""
    H = len(grid); W = len(grid[0])
    hs = [[1 if grid[r][c] == HIGHSTONE else 0 for c in range(W)] for r in range(H)]
    er = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if hs[r][c] and all(hs[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                er[r][c] = 1
    di = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if any(er[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                di[r][c] = 1
    for r in range(H):
        for c in range(W):
            if grid[r][c] == HIGHSTONE and not di[r][c]:
                grid[r][c] = GRASS
            elif di[r][c] and grid[r][c] in (GRASS, DIRT, MUD, HIGHGRASS, SAND, STONE):
                grid[r][c] = HIGHSTONE


# 参与修边的全部地形（含水/高石；autotile 四角拼接下对角相接 OK，但孤立尖刺与
# "仅对角相连"伪影必须收拾，详见 references/edge_cleanup.md §A）。
_PAINT = {GRASS, DIRT, STONE, SAND, MUD, HIGHGRASS, HIGHSTONE, SHOAL, WATER, SEA, OCEAN}
ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def clean_all(grid, iters=3):
    """通用修边（edge cleanup）：原地修改全部地形。

    逐细胞检查 8 邻同类数：
      - cnt<3（孤立尖刺/1 格颈）            → 并入主导邻类（最严格规则下仍保持连通）
      - cnt>=3 但正交无同类、仅对角有同类   → 打断"仅对角相连"伪影，并入多数正交邻
    越界邻居按"与当前同类"处理，使地图最外一圈也能被修边（避免边缘残留 1 格突刺）。
    2 轮迭代已足够把尖刺/伪影压平，又不破坏 ≥2 格宽的通道与山体。
    """
    H = len(grid); W = len(grid[0])
    ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
    DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))

    def _get(r, c, cat):
        if 0 <= r < H and 0 <= c < W:
            return grid[r][c]
        return cat  # 越界视作同类，不惩罚边界

    for _ in range(iters):
        changes = []
        for r in range(H):
            for c in range(W):
                cat = grid[r][c]
                if cat not in _PAINT:
                    continue
                orth = [_get(r + dr, c + dc, cat) for dr, dc in ORTH]
                diag = [_get(r + dr, c + dc, cat) for dr, dc in DIAG]
                cnt = sum(1 for x in orth + diag if x == cat)
                if cnt < 3:
                    pool = [x for x in orth + diag if x in _PAINT]
                    if not pool:
                        continue
                    dom = Counter(pool).most_common(1)[0][0]
                    if dom != cat:
                        changes.append((r, c, dom))
                elif cat not in orth and any(x == cat for x in diag):
                    co = [x for x in orth if x in _PAINT]
                    if co:
                        dom = Counter(co).most_common(1)[0][0]
                        if dom != cat:
                            changes.append((r, c, dom))
        for (r, c, v) in changes:
            grid[r][c] = v
    return grid


def detail_land(grid, rng):
    """陆地细分层：双噪声打碎纯草连片，使草地不成绿板；两侧分别落不同的次级地貌。"""
    H = W = SIZE
    for r in range(H):
        for c in range(W):
            if grid[r][c] != GRASS:
                continue
            side = 0 if c < 100 else 1
            ox = 200 if side == 0 else 900
            elev = _fbm(r + ox, c + ox, ((1 / 52.0, 0.55), (1 / 25.0, 0.45)))
            micro = _vn(r, c, 1 / 8.0)
            if side == 0:
                if elev > 0.46:
                    grid[r][c] = DIRT
                elif elev < -0.40:
                    grid[r][c] = HIGHGRASS
                elif elev < -0.26:
                    grid[r][c] = MUD
            else:
                if elev > 0.18:
                    grid[r][c] = SAND
                elif elev < -0.46:
                    grid[r][c] = DIRT
            if grid[r][c] == GRASS:
                a = _vn(r, c, 1 / 9.0)
                b = _vn(r, c + 313, 1 / 7.0)
                if a > 0.24:
                    grid[r][c] = DIRT if side == 0 else SAND
                elif b < -0.24:
                    grid[r][c] = HIGHGRASS


def protect_bases(grid, spawns):
    H = len(grid); W = len(grid[0])
    for (sr, sc, _t) in spawns:
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 3:
                    if grid[r][c] in IMPASS:
                        grid[r][c] = GRASS


def place_res(items, grid, spawns):
    H = len(grid); W = len(grid[0])
    for (sr, sc, _t) in spawns:
        for (dr, dc) in ((-2, -2), (2, 2)):
            tr, tc = sr + dr, sc + dc
            if not (0 <= tr < H and 0 <= tc < W and grid[tr][tc] not in IMPASS):
                found = None
                for rad in range(1, 7):
                    for dd in ((dr + rad, dc), (dr - rad, dc), (dr, dc + rad), (dr, dc - rad)):
                        r, c = sr + dd[0], sc + dd[1]
                        if 0 <= r < H and 0 <= c < W and grid[r][c] not in IMPASS:
                            found = (r, c); break
                    if found:
                        break
                if not found:
                    continue
                tr, tc = found
            grid[tr][tc] = GRASS
            items[tr][tc] = 1


# ---- 装饰道具 v3（V4.1 实测定案：逐格 alpha 扫描 + 8x 放大肉眼核对）----
# 【铁律】装饰层/物品层只允许放「透明底花草树道具」。
#  满格不透明硬贴片(带方形底色)铺上去就是一块块色斑补丁，严禁使用！
#
# ✅ 透明底白名单（op<300/400 且四角 alpha=0，已逐格实测）：
#   草簇/花:  711 712 714 898        树:  890 891(绿松) 746(枯树)
#   岩石:     713 718 719 754 755    尖柱: 854 855
#   枯根:     935
#   冰雪图专用: 860 1006 1007 1042 1043（蓝白冰晶/冰山，非雪地图禁用）
#
# ❌ 硬贴片黑名单（op≈400/400 满格不透明，带方形底色）：
#   823 859(雪地+树贴片!) 826(土+岩) 934(棕根满格) 971(岩纹)
#   1078 1079(冰雪地块) 499(草皮纹理)
# ❌ 无效/危险格：818 861(几乎全空 op≤4)、1089(问号图标) 1095 1096 1097(A/R/R2
#   字母图标)、≥1080(超出 tsx tilecount=1080)
TUFT1, TUFT2, TUFT3, TUFT4 = 711, 712, 714, 898      # 草簇/幼苗/小花
PINE1, PINE2, DEADTREE = 890, 891, 746               # 透明底绿松/枯树
BOULDER1, BOULDER2, ROCKS, FORM = 718, 719, 754, 713 # 巨岩/石堆/褐岩
SPIRE1, SPIRE2 = 854, 855                            # 黑岩尖柱
ROOT = 935                                           # 枯根
ICE_TREES = [860, 1006, 1007, 1042, 1043]            # 仅雪原图专用
# 兼容旧名（林海雪岭等）
TUFT, PINE_S, PINE_D, PINE_L = TUFT1, PINE1, PINE2, PINE1
# 装饰层最终安全池（程序自动校验用，详见 scripts/check_decor_tiles.py）
DECOR_SAFE = {711, 712, 714, 898, 890, 891, 746, 718, 719, 754, 713, 854, 855, 935}
DECOR_SNOW = {860, 1006, 1007, 1042, 1043}
DECOR_BANNED = {823, 826, 859, 934, 971, 1078, 1079, 499, 818, 861,
                1089, 1090, 1095, 1096, 1097} | set(range(1080, 1116))


def make_decor(grid, rng, opts=None):
    """装饰层 v2：全部使用透明底道具，成簇成片分布。

    旧版逐格独立随机 + 带底色贴片(826/934/499) → 满图黄白方块"芝麻补丁"。
    新版：按地貌投放『林丛/石滩/灌丛/草簇』簇，开阔地留白，疏密自然。
    opts:
      density      总密度系数（默认 1.0）
      forest_tiles 高草(林丛)用道具，默认雪松；干旱图传 [FORM,ROOT,...] 灌丛
      sand_tiles   沙地用道具
    """
    H = W = SIZE
    decor = [[0] * W for _ in range(H)]
    o = opts or {}
    dens = o.get("density", 1.0)
    forest = o.get("forest_tiles", [PINE_S, PINE_D, PINE_S, PINE_L])
    sand_tiles = o.get("sand_tiles", [FORM, ROCKS, TUFT1])
    mud_tiles = o.get("mud_tiles", [TUFT2, ROCKS])
    # stone_decor=False（国家图专用）：山地本身已是石头纹理，再撒巨岩石堆
    # 就是"石头上放石头"，密密麻麻非常突兀 —— 跳过石滩/尖柱簇，只留花草树。
    stone_decor = o.get("stone_decor", True)
    cells = {}
    for r in range(2, H - 2):
        for c in range(2, W - 2):
            cells.setdefault(grid[r][c], []).append((r, c))

    def scatter(terrs, tiles, n_cl, size_lo, size_hi, sigma, p_place=0.85):
        pool = [rc for t in terrs if cells.get(t) for rc in cells[t]]
        if not pool:
            return 0
        placed = 0
        for _ in range(max(1, int(n_cl * dens))):
            cr, cc = pool[rng.randrange(len(pool))]
            for _ in range(rng.randint(size_lo, size_hi)):
                rr = cr + int(round(rng.gauss(0, sigma)))
                cc2 = cc + int(round(rng.gauss(0, sigma)))
                if not (2 <= rr < H - 2 and 2 <= cc2 < W - 2):
                    continue
                if grid[rr][cc2] not in terrs or decor[rr][cc2]:
                    continue
                if rng.random() < p_place:
                    decor[rr][cc2] = GROUND_FG + tiles[rng.randrange(len(tiles))]
                    placed += 1
        return placed

    cnt = {t: len(v) for t, v in cells.items()}
    # 林丛/灌丛：高草地上成片
    scatter([HIGHGRASS], list(forest) + [TUFT2],
            cnt.get(HIGHGRASS, 0) / 90, 5, 13, 2.2)
    if stone_decor:
        # 石滩：石地/崖壁上的巨岩与石堆群
        scatter([STONE, HIGHSTONE], [BOULDER1, BOULDER2, ROCKS],
                (cnt.get(STONE, 0) + cnt.get(HIGHSTONE, 0)) / 120, 4, 10, 2.0)
        # 崖壁尖柱：少量黑岩柱增加峭壁感
        scatter([HIGHSTONE], [SPIRE1, SPIRE2], cnt.get(HIGHSTONE, 0) / 400, 1, 3, 1.4)
    # 沙地：褐岩造型 + 小石堆 + 稀疏草簇
    scatter([SAND], list(sand_tiles), cnt.get(SAND, 0) / 220, 2, 6, 2.4)
    # 泥地/土径：稀疏草簇与孤石
    scatter([DIRT, MUD], list(mud_tiles), (cnt.get(DIRT, 0) + cnt.get(MUD, 0)) / 260, 2, 5, 1.8)
    # 开阔草地：只留零星草簇（几乎没有，保持净空）
    scatter([GRASS], [TUFT1, TUFT2], cnt.get(GRASS, 0) / 700, 2, 4, 1.6)
    return decor


def bfs_dist(grid, sr, sc):
    H = W = SIZE
    dist = [[-1] * W for _ in range(H)]
    if grid[sr][sc] in IMPASS:
        return dist
    q = deque([(sr, sc)]); dist[sr][sc] = 0
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and dist[rr][cc] < 0 and grid[rr][cc] not in IMPASS:
                dist[rr][cc] = dist[r][c] + 1; q.append((rr, cc))
    return dist


def largest_grass_cc(grid):
    H = W = SIZE
    seen = [[False] * W for _ in range(H)]
    best = 0
    for r in range(H):
        for c in range(W):
            if grid[r][c] == GRASS and not seen[r][c]:
                cnt = 0
                q = deque([(r, c)]); seen[r][c] = True
                while q:
                    rr, cc = q.popleft(); cnt += 1
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and grid[nr][nc] == GRASS:
                            seen[nr][nc] = True; q.append((nr, nc))
                best = max(best, cnt)
    return best


def edge_metrics(grid):
    """修边质量量化（详见 references/edge_cleanup.md §J.2）。
    返回值越低越好：iso=孤立尖刺(8邻同类<3)、cnt0=完全悬空(0同类)、diagonly=仅对角相连伪影。"""
    H = len(grid); W = len(grid[0])
    iso = cnt0 = diagonly = 0
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            cat = grid[r][c]
            if cat not in _PAINT:
                continue
            orth = [grid[r + dr][c + dc] for dr, dc in ORTH]
            diag = [grid[r + dr][c + dc] for dr, dc in DIAG]
            cnt = sum(1 for x in orth + diag if x == cat)
            if cnt < 3:
                iso += 1
            if cnt == 0:
                cnt0 += 1
            if cat not in orth and any(x == cat for x in diag):
                diagonly += 1
    return iso, cnt0, diagonly


def central_open_share(grid, c0=60, c1=140, r0=60, r1=140):
    """中央 80×80 内开阔地形（草/土/沙/浅滩）合计占比，越低越抑空军。"""
    H = W = SIZE
    OPEN = {GRASS, DIRT, SAND, SHOAL}
    tot = (r1 - r0) * (c1 - c0)
    n = 0
    for r in range(r0, r1):
        for c in range(c0, c1):
            if grid[r][c] in OPEN:
                n += 1
    return 100 * n / tot if tot else 0


def central_max_terrain(grid, c0=60, c1=140, r0=60, r1=140, open_only=True):
    """中央区『开阔地形』主导度（抑空军红线）。

    只统计开阔可轰炸地形：草/土/沙/浅滩(23)。高草(森林)/石/高石(崖壁)属于
    掩体，越多越利于抑空军，不计入『开阔』。返回中央 80×80 内开阔地形单类最大占比。"""
    H = W = SIZE
    OPEN = {GRASS, DIRT, SAND, SHOAL}
    cnt = Counter()
    for r in range(r0, r1):
        for c in range(c0, c1):
            t = grid[r][c]
            if open_only and t not in OPEN:
                continue
            cnt[t] += 1
    tot = (r1 - r0) * (c1 - c0)
    return max(cnt.values()) / tot * 100 if tot else 0


def verify_connectivity(grid, spawns, bands):
    """bands: list of (r0,r1,c0,c1) 矩形，每个是一条地面通道。
    逐条封锁（置 HIGHSTONE）后检验左右仍连通，统计独立通道数。"""
    base = bfs_dist(grid, spawns[0][0], spawns[0][1])
    reachable = all(base[sr][sc] >= 0 for (sr, sc, _t) in spawns)
    sp = [(sr, sc) for sr, sc, _t in spawns]
    pair_ok = True
    for i in range(len(sp)):
        d = bfs_dist(grid, sp[i][0], sp[i][1])
        for j in range(len(sp)):
            if d[sp[j][0]][sp[j][1]] < 0:
                pair_ok = False
    cd = bfs_dist(grid, 100, 100)
    left = [cd[sr][sc] for (sr, sc, t) in spawns if t % 2 == 0]
    right = [cd[sr][sc] for (sr, sc, t) in spawns if t % 2 == 1]
    la, ra = (sum(left) / len(left)), (sum(right) / len(right))
    bal_diff = abs(la - ra) / max(la, ra) * 100 if max(la, ra) else 0
    n_pass = 0
    for bi, (r0, r1, c0, c1) in enumerate(bands):
        g2 = [row[:] for row in grid]
        for rr in range(r0, r1 + 1):
            for cc in range(c0, c1 + 1):
                if 0 <= rr < SIZE and 0 <= cc < SIZE:
                    g2[rr][cc] = HIGHSTONE
        sd = bfs_dist(g2, spawns[0][0], spawns[0][1])
        ok = any(sd[sr][sc] >= 0 for (sr, sc, t) in spawns if t % 2 == 1)
        if ok:
            n_pass += 1
    return {"reachable": reachable, "pair_ok": pair_ok, "bal_diff": bal_diff,
            "left_avg": la, "right_avg": ra, "passages": n_pass}


def edge_pass_rate(grid):
    """修边正确率（V4.1 门槛：≥98% 才允许出图）。

    bad = 孤立尖刺 + 悬空 + 仅对角伪影（edge_metrics 口径）；
    pass_rate = 1 - bad / 内部可检格数((H-2)*(W-2))。
    """
    H = len(grid); W = len(grid[0])
    iso, cnt0, diagonly = edge_metrics(grid)
    interior = max(1, (H - 2) * (W - 2))
    bad = iso + cnt0 + diagonly
    return 100.0 * (1 - bad / interior), iso, cnt0, diagonly


def edge_auto_fix(grid, threshold=98.0, max_iters=8):
    """自动修复修边直到正确率 ≥ threshold（默认 98%），原地修改。

    返回 (pass_rate, iso, cnt0, diagonly, iters)。达 max_iters 仍不达标则抛
    RuntimeError —— 宁可不出图，也不出带毛边的图。"""
    rate = iso = cnt0 = diagonly = 0.0
    it = 0
    for it in range(1, max_iters + 1):
        clean_all(grid, iters=1)
        rate, iso, cnt0, diagonly = edge_pass_rate(grid)
        if rate >= threshold:
            return rate, iso, cnt0, diagonly, it
    if rate < threshold:
        raise RuntimeError(
            f"修边正确率 {rate:.2f}% < {threshold}%（iso={iso} cnt0={cnt0} diagonly={diagonly}），"
            f"已自动修复 {max_iters} 轮仍不达标 —— 拒绝出图，请检查地形生成逻辑")
    return rate, iso, cnt0, diagonly, it


# 触发器/单位 schema（V4.1：从 classes.dex + 官方自带地图双重核对）
TRIGGER_TYPES = {"unitDetect", "unitAdd", "unitRemove", "basic", "mapText",
                 "changeCredits", "teamTags", "team_info", "camera_start"}
TRIGGER_OBJ_NAMES = {"map_info", "camera_start", "team_info"}
WIN_CONDITIONS = {"mainBuilings", "mainBuildings", "noBuildRadius", "captureTheFlag"}
FOG_MODES = {"los", "map", "off"}
TRIGGER_PROPS = {
    "type", "winCondition", "fog", "introText", "credits", "team", "allyGroup",
    "unitType", "minUnits", "maxUnits", "spawnUnits", "activatedBy",
    "resetActivationAfter", "globalMessage", "warmup", "action", "text",
    "textSize", "textColor", "teamTags", "amount", "showFog",
}
UNITOBJ_PROPS = {"team", "unit"}


def _load_unit_names():
    """从 references/单位表_1.15.txt 提取全部合法单位内部名（♢标记）。"""
    import re
    names = set()
    path = os.path.join(HERE, "references", "单位表_1.15.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                names.update(re.findall(r"♢([A-Za-z_][A-Za-z0-9_]*)", line))
    except OSError:
        pass
    names.update({"commandCenter", "builder", "crystalResource", "tree"})  # 地图必备
    return names


def validate_triggers(tree, teams=None):
    """触发器/单位零错误校验（V4.1）。

    检查项：
      1. Triggers 组：map_info 存在且 type=skirmish；winCondition/fog 拼写合法
         （winCondition 官方拼写就是 mainBuilings —— dex 里两种都有，以官图为准）；
         触发器 type 与属性名在白名单内；object id 不重复。
      2. UnitObjects 组：每个参赛队恰好 ≥1 个 commandCenter（winCondition 要求
         主建筑开局即存在，unitAdd 来不及）；unit 名在 单位表_1.15.txt 白名单内；
         属性只有 team/unit。
      3. camera_start 存在。
    返回问题列表（空 = 通过）。
    """
    issues = []
    root = tree.getroot()
    ogs = {g.get("name"): g for g in root.findall("objectgroup")}
    trig = ogs.get("Triggers")
    seen_ids = set()
    if trig is None:
        issues.append("Triggers: 缺少 Triggers objectgroup")
    else:
        has_map_info = False
        for o in trig.findall("object"):
            oid = o.get("id")
            if oid in seen_ids:
                issues.append(f"Triggers: object id 重复 {oid}")
            seen_ids.add(oid)
            nm, typ = o.get("name"), o.get("type") or ""
            props = {p.get("name"): p.get("value")
                     for p in o.findall("properties/property")}
            if nm == "map_info":
                has_map_info = True
                if props.get("type") != "skirmish":
                    issues.append(f"map_info: type={props.get('type')!r} 应为 'skirmish'")
                wc = props.get("winCondition")
                if wc and wc not in WIN_CONDITIONS:
                    issues.append(f"map_info: winCondition={wc!r} 非法（官方拼写 mainBuilings）")
                fog = props.get("fog")
                if fog and fog not in FOG_MODES:
                    issues.append(f"map_info: fog={fog!r} 非法（los/map/off）")
            else:
                if typ and typ not in TRIGGER_TYPES:
                    issues.append(f"Triggers/{nm}: 未知触发器类型 {typ!r}")
                bad = set(props) - TRIGGER_PROPS
                if bad:
                    issues.append(f"Triggers/{nm}: 非法属性 {sorted(bad)}")
        if not has_map_info:
            issues.append("Triggers: 缺少 map_info")
        if not any(o.get("name") == "camera_start" or o.get("type") == "camera_start"
                   for o in trig.findall("object")):
            issues.append("Triggers: 缺少 camera_start")
    uo = ogs.get("UnitObjects")
    if uo is None:
        issues.append("UnitObjects: 缺少 UnitObjects objectgroup")
    else:
        cc_by_team, unit_names = {}, _load_unit_names()
        for o in uo.findall("object"):
            props = {p.get("name"): p.get("value")
                     for p in o.findall("properties/property")}
            bad = set(props) - UNITOBJ_PROPS
            if bad:
                issues.append(f"UnitObjects#{o.get('id')}: 非法属性 {sorted(bad)}")
            unit = props.get("unit", "")
            if unit not in unit_names:
                issues.append(f"UnitObjects#{o.get('id')}: 未知单位名 {unit!r}")
            team = props.get("team")
            if unit == "commandCenter":
                cc_by_team[team] = cc_by_team.get(team, 0) + 1
        if teams:
            for t in teams:
                if cc_by_team.get(str(t), 0) < 1:
                    issues.append(f"UnitObjects: 队伍 {t} 缺 commandCenter（会被判负）")
    return issues


def write_tmx(grid, decor, items, spawns, crystals, out, intro=""):
    SIZE_ = SIZE
    ground_tid = C.autotile(grid)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(SIZE_)] for r in range(SIZE_)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(SIZE_)] for r in range(SIZE_)]

    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(SIZE_), "height": str(SIZE_),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())

    def enc(data):
        raw = struct.pack("<%dI" % (SIZE_ * SIZE_), *[data[r][c] for r in range(SIZE_) for c in range(SIZE_)])
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * SIZE_ for _ in range(SIZE_)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(SIZE_), "height": str(SIZE_)})
        d = ET.SubElement(l, "data", {"encoding": "base64", "compression": "gzip"})
        d.text = enc(data)

    og = ET.SubElement(map_el, "objectgroup", {"name": "Triggers"})
    nid = [1]

    def add_obj(name, typ, x, y, props, w=20, hh=20):
        o = ET.SubElement(og, "object", {"id": str(nid[0]), "name": name, "type": typ,
                                         "x": str(x), "y": str(y), "width": str(w), "height": str(hh)})
        nid[0] += 1
        p = ET.SubElement(o, "properties")
        for k, v in props.items():
            ET.SubElement(p, "property", {"name": k, "value": str(v)})
        return o

    add_obj("map_info", "", SIZE_ // 2, SIZE_ // 2 - 20, {
        "type": "skirmish",
        "winCondition": "mainBuilings",
        "fog": "los",
        "introText": intro,
    }, 224, 136)

    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid_u = [100]

    def add_unit(unit, team, x, y):
        o = ET.SubElement(uo, "object", {"id": str(nid_u[0]), "x": str(x), "y": str(y),
                                         "width": "20", "height": "20"})
        nid_u[0] += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": unit})

    for (sr, sc, team) in spawns:
        sx, sy = sc * 20, sr * 20
        add_unit("commandCenter", team, sx, sy)
        back = -1 if sc < 100 else 1
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    for (rr, cc) in crystals:                      # (row, col) → x=列*20, y=行*20
        add_unit("crystalResource", -1, cc * 20, rr * 20)

    add_obj("camera_start", "camera_start", 100 * 20, SIZE_ // 2 * 20, {}, 20, 20)

    max_oid = 0
    for g in map_el.findall("objectgroup"):
        for o in g.findall("object"):
            try:
                max_oid = max(max_oid, int(o.get("id", 0)))
            except ValueError:
                pass
    map_el.set("nextobjectid", str(max_oid + 1))

    tree = ET.ElementTree(map_el)
    fgmap = {C.TSX: (GROUND_FG, MERGED_COUNT)}
    issues = K.validate_tmx(tree, SIZE_, SIZE_, fgmap, [(sr, sc) for sr, sc, _ in spawns])
    issues += validate_triggers(tree, teams=sorted({t for _, _, t in spawns}))
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, issues


def get_spawns():
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, TEAMS_L)] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, TEAMS_R)])


NM = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 12: "高草", 14: "高石",
      7: "水", 8: "海", 9: "洋", 23: "浅滩"}


def report(grid, items, decor, crystals, spawns, v, issues, label=""):
    terr = Counter()
    for row in grid:
        for vv in row:
            terr[vv] += 1
    total = SIZE * SIZE
    ndec = sum(1 for row in decor for vv in row if vv)
    grass_cc = largest_grass_cc(grid)
    ctr = central_max_terrain(grid)                     # 开阔地形主导度（抑空军）
    open_share = central_open_share(grid)
    iso, cnt0, diagonly = v.get("edge", edge_metrics(grid))  # 优先纯地形修边指标（铺点前）
    rate = 100.0 * (1 - (iso + cnt0 + diagonly) / max(1, (SIZE - 2) * (SIZE - 2)))
    print(f"\n===== 自检报告 {label} =====")
    print(f"尺寸: {SIZE}x{SIZE}")
    print("地形分布(top6):", {NM.get(k, k): f"{cnt/total*100:.1f}%" for k, cnt in terr.most_common(6)})
    print(f"地形类别数={len(terr)}  最大占比={max(terr.values())/total*100:.1f}%")
    print(f"草地最大连片={grass_cc}格 ({100*grass_cc/total:.1f}%)  中央开阔度(草/土/沙)={open_share:.1f}%  开阔单类峰值={ctr:.1f}%")
    print(f"修边指标: 孤立尖刺iso={iso} 悬空cnt0={cnt0} 对角伪影diagonly={diagonly} -> 正确率={rate:.2f}% (门槛98%)")
    print(f"连通: 10点互达={v['reachable']} 两两互达={v['pair_ok']}")
    print(f"平衡: 左均距={v['left_avg']:.0f} 右均距={v['right_avg']:.0f} 差异={v['bal_diff']:.1f}%")
    print(f"地面通道数={v['passages']}  起步矿={sum(sum(row) for row in items)}(左右各{sum(sum(row) for row in items)//2})  水晶={len(crystals)}")
    print(f"装饰密度={ndec}格 ({100*ndec/total:.2f}%)")
    print("校验问题:", issues if issues else "无")
    return {"types": len(terr), "maxpct": max(terr.values())/total*100,
            "grass_cc": grass_cc/total*100, "ctr": ctr, "ndec": 100*ndec/total,
            "iso": iso, "cnt0": cnt0, "diagonly": diagonly, "edge_rate": rate}
