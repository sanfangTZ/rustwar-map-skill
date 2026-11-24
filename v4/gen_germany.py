#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭空画德国 · 自然主义地理写实遭遇战图 v2

数据来源：本 Skill 的 `references/country_geo_europe.md` 德国条目（纯文本地理简报）。
把"位置/轮廓/一级行政区/地势地形/画此国提示"五字段直接当地形种子落地成可玩 .tmx。

v2 改进（针对 v1"几何直线 + 色块拼图"的丑）：
- 连续噪声高度场 + 阈值映射 → 海陆自然渐变、不再硬切
- 蜿蜒河流（正弦 + 噪声扰动），每 ~11 格留徒涉口保证陆地连通
- 弯曲海岸线（低频 + 中频噪声叠加）
- 连绵山脉带（局部高斯抬升，而非孤立圆团）
- 陆地明暗斑块（草/土/泥/高草斑驳，非纯色块）
- 湖泊（博登湖/北部湖等）
- 预览叠加河流名标注，更像"地图"

地形角索引（地面层整合.tsx）：
  0草 1土 2石 3沙 4泥 7水 8海 9洋 12高草 14高石(高山/cliff) 23浅滩
坐标约定：row 0 = 北(顶) / row H-1 = 南(底)；col 0 = 西(左) / col W-1 = 东(右)。
"""
import os, struct, base64, gzip, random, math
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gen_combined as C
import gen_koth as K

GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14

H, W = 220, 160                       # 南北长（德国 876×640km ≈ 1.37:1）
COAST_BASE = 17                       # 北部海岸基准行（之上有海），由海岸线噪声扰动
BOTTOM = H - 1

# 8 城 FFA 出生点 (城市, 行, 列, team)
CITIES = [
    ("柏林", 70, 95, 0), ("汉堡", 26, 66, 1), ("慕尼黑", 172, 82, 2),
    ("科隆", 56, 40, 3), ("法兰克福", 74, 50, 4), ("斯图加特", 138, 50, 5),
    ("莱比锡", 84, 106, 6), ("不来梅", 34, 58, 7),
]
# 中立争夺水晶（鲁尔/萨克森/巴伐利亚）
CRYSTALS = [(58, 44), (112, 112), (150, 86)]

# 局部山脉高斯抬升（哈茨/图林根/黑森林/巴伐利亚林山/厄尔士/威悉/阿尔高前山）
RANGES = [
    (95, 80, 13, 0.42),    # 哈茨
    (112, 76, 12, 0.40),   # 图林根林山
    (140, 52, 14, 0.42),   # 黑森林
    (150, 118, 13, 0.40),  # 巴伐利亚林山
    (120, 124, 12, 0.38),  # 厄尔士山（捷克边境东）
    (100, 60, 11, 0.30),   # 威悉山
    (162, 150, 12, 0.38),  # 阿尔高 / 阿尔卑斯前山
]


# ---------- 确定性噪声 ----------
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
    """中频 fbm（丘陵/山谷）。"""
    return 0.55 * _vn(r, c, 1 / 26.0) + 0.30 * _vn(r, c, 1 / 13.0) + 0.15 * _vn(r, c, 1 / 6.0)

def _noise_lo(r, c):
    """低频（大陆级起伏）。"""
    return 0.6 * _vn(r, c, 1 / 90.0) + 0.4 * _vn(r, c, 1 / 42.0)

def _noise_hi(r, c):
    """高频（地表斑驳纹理）。"""
    return _vn(r, c, 1 / 5.0)


def coastband(c):
    """北部海岸线行（之上有海）。低频 + 中频噪声 → 弯曲自然海岸。"""
    return COAST_BASE + 9.0 * _vn(0, c, 1 / 38.0) + 4.0 * _vn(0, c + 50, 1 / 14.0)


def _disk(grid, cr, cc, rad, cat, ring=None):
    R = math.ceil(rad) + 1
    for r in range(max(0, cr - R), min(H, cr + R + 1)):
        for c in range(max(0, cc - R), min(W, cc + R + 1)):
            d = math.hypot(r - cr, c - cc)
            if d <= rad:
                grid[r][c] = cat
            elif ring is not None and d <= rad + 1.2:
                if grid[r][c] not in (WATER, SEA, OCEAN, HIGHSTONE):
                    grid[r][c] = ring


def _wavy(r0, c0, r1, c1, amp, freq, phase, perp='c'):
    """生成蜿蜒路径：沿直线插值后，在垂直轴加正弦 + 噪声偏移。"""
    steps = int(max(abs(r1 - r0), abs(c1 - c0))) + 1
    out = []
    for i in range(steps + 1):
        t = i / steps
        r = r0 + (r1 - r0) * t
        c = c0 + (c1 - c0) * t
        off = amp * math.sin(t * math.pi * freq + phase) + 2.5 * _noise(int(r * 0.25), int(c * 0.25) + int(phase * 10))
        if perp == 'c':
            c = c + off
        else:
            r = r + off
        out.append((int(round(r)), int(round(c))))
    return out

def _carve(grid, pts, ford=11, width=1):
    """沿路径雕刻河流：宽 width，每 ford 步留 2 格草洲徒涉口（保证陆军可直穿）。
    遇 HIGHSTONE 不强行挖河（避免切山）。"""
    for idx, (r, c) in enumerate(pts):
        if not (0 <= r < H and 0 <= c < W):
            continue
        is_ford = (idx % ford) < 2
        cells = [(r, c)]
        if width > 1:
            cells.append((r, c + 1 if c + 1 < W else c - 1))
        for (rr, cc) in cells:
            if 0 <= rr < H and 0 <= cc < W and grid[rr][cc] != HIGHSTONE:
                grid[rr][cc] = GRASS if is_ford else WATER


def build_terrain(seed):
    rng = random.Random(seed)
    # 1) 连续噪声高度场：南高北低梯度 + 阿尔卑斯抬升 + 大陆起伏 + 局部山脉凸起
    field = np.zeros((H, W), dtype=float)
    for r in range(H):
        lat = r / BOTTOM                       # 0 北 .. 1 南
        alps = max(0.0, lat - 0.78) * 6.0       # 最南阿尔卑斯额外抬升
        for c in range(W):
            g = lat * 0.62 + alps * 0.55 + 0.38 * _noise_lo(r, c) + 0.14 * _noise(r, c)
            for (cr, cc, sg, am) in RANGES:
                g += am * math.exp(-((r - cr) ** 2 + (c - cc) ** 2) / (2 * sg * sg))
            field[r][c] = g

    grid = np.full((H, W), GRASS, dtype=int)

    # 2) 北部北海/波罗的海：弯曲海岸线 + 环状分层（洋→海→水→浅滩→沙）
    for c in range(W):
        cb = coastband(c)
        for r in range(H):
            if r < cb:
                d = cb - r
                grid[r][c] = (OCEAN if d > 11 else SEA if d > 6
                              else WATER if d > 3 else SHOAL if d > 1 else SAND)

    # 3) 陆地地形映射（连续场阈值 → 自然过渡，非硬分区）
    for r in range(H):
        lat = r / BOTTOM
        for c in range(W):
            cur = grid[r][c]
            if cur in (OCEAN, SEA, WATER, SHOAL, SAND):
                continue
            f = field[r][c]
            if lat > 0.78 and f > 1.12:
                grid[r][c] = HIGHSTONE                      # 阿尔卑斯主峰带
            elif f > 0.96:
                grid[r][c] = STONE                         # 中等山地
            else:
                m = _noise_hi(r, c); hh = _noise(r, c)
                if m < -0.72:
                    grid[r][c] = MUD                       # 洼地/沼泽（少量）
                elif m > 0.60:
                    grid[r][c] = HIGHGRASS                 # 草丛/疏林
                elif hh > 0.32:
                    grid[r][c] = DIRT                      # 土斑（斑驳质感）
                # else 保持 GRASS

    # 4) 蜿蜒河流（莱茵/易北/多瑙），带徒涉渡口
    _carve(grid, _wavy(176, 54, 16, 42, amp=5, freq=1.2, phase=0.7, perp='c'), ford=11)
    _carve(grid, _wavy(122, 108, 24, 64, amp=6, freq=1.0, phase=2.1, perp='c'), ford=11)
    _carve(grid, _wavy(180, 86, 176, W - 3, amp=4, freq=2.0, phase=1.3, perp='r'), ford=11)

    # 5) 湖泊（博登湖/北部湖/东南湖/西南湖），外圈浅滩过渡
    for (lr, lc, rad) in [(177, 96, 4.2), (30, 120, 3.2), (150, 150, 3.4), (60, 30, 3.0)]:
        _disk(grid, lr, lc, rad, WATER, ring=SHOAL)

    # 6) 清理：高草孤片回填草；高石开运算去毛刺（沿用修边经验）
    _clean_small(grid, HIGHGRASS, 8, GRASS)
    _open_close(grid, HIGHSTONE, GRASS)

    return grid, rng


def _clean_small(grid, cat, minsz, fill):
    Hh, Ww = grid.shape
    seen = [[0] * Ww for _ in range(Hh)]
    for r0 in range(Hh):
        for c0 in range(Ww):
            if grid[r0][c0] == cat and not seen[r0][c0]:
                stack = [(r0, c0)]; seen[r0][c0] = 1; cells = []
                while stack:
                    r, c = stack.pop(); cells.append((r, c))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < Hh and 0 <= cc < Ww and grid[rr][cc] == cat and not seen[rr][cc]:
                            seen[rr][cc] = 1; stack.append((rr, cc))
                if len(cells) < minsz:
                    for r, c in cells:
                        grid[r][c] = fill


def _open_close(grid, cat, fill):
    """开运算去毛刺/孤块 → 膨胀补回轮廓（山体边缘圆润）。"""
    Hh, Ww = grid.shape
    m = [[1 if grid[r][c] == cat else 0 for c in range(Ww)] for r in range(Hh)]
    er = [[0] * Ww for _ in range(Hh)]
    for r in range(1, Hh - 1):
        for c in range(1, Ww - 1):
            if m[r][c] and all(m[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                er[r][c] = 1
    di = [[0] * Ww for _ in range(Hh)]
    for r in range(1, Hh - 1):
        for c in range(1, Ww - 1):
            if any(er[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                di[r][c] = 1
    for r in range(Hh):
        for c in range(Ww):
            if grid[r][c] == cat and not di[r][c]:
                grid[r][c] = fill
            elif di[r][c] and grid[r][c] in (GRASS, DIRT, MUD, HIGHGRASS, STONE, SAND):
                grid[r][c] = cat


def get_spawns():
    return [(r, c, t) for (_name, r, c, t) in CITIES]


def protect_bases(grid, spawns):
    for (sr, sc, _t) in spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 2:
                    if grid[r][c] in (WATER, SEA, OCEAN, SHOAL, HIGHSTONE, MUD, HIGHGRASS):
                        grid[r][c] = GRASS


def place_res(items, grid, spawns):
    for (sr, sc, _t) in spawns:
        for (dr, dc) in ((-2, -2), (2, 2)):
            tr, tc = sr + dr, sc + dc
            if not (0 <= tr < H and 0 <= tc < W and grid[tr][tc] not in
                    (WATER, SEA, OCEAN, SHOAL, HIGHSTONE, MUD, HIGHGRASS)):
                found = None
                for rad in range(1, 6):
                    for dd in ((dr + rad, dc), (dr - rad, dc), (dr, dc + rad), (dr, dc - rad)):
                        r, c = sr + dd[0], sc + dd[1]
                        if 0 <= r < H and 0 <= c < W and grid[r][c] not in \
                                (WATER, SEA, OCEAN, SHOAL, HIGHSTONE, MUD, HIGHGRASS):
                            found = (r, c); break
                    if found:
                        break
                if not found:
                    continue
                tr, tc = found
            grid[tr][tc] = GRASS
            items[tr][tc] = 1


def make_decor(grid, rng):
    decor = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == MUD and _noise(r + 8000, c - 8000) > 0.5:
                decor[r][c] = 1 + 934                       # 枯木（泥地同色系）
            elif grid[r][c] == STONE and _noise(r + 6000, c + 6000) > 0.62:
                decor[r][c] = 1 + 826                       # 岩石（石坡点缀，避高石）
    return decor


def generate(seed=7, out="rw_germany.tmx"):
    grid, rng = build_terrain(seed)
    spawns = get_spawns()
    protect_bases(grid, spawns)
    items = [[0] * W for _ in range(H)]
    place_res(items, grid, spawns)
    decor = make_decor(grid, rng)

    ground_tid = C.autotile(grid)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(W)] for r in range(H)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(W)] for r in range(H)]

    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(W), "height": str(H),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())

    def enc(data):
        flat = [data[r][c] for r in range(H) for c in range(W)]
        raw = struct.pack("<%dI" % (H * W), *flat)
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * W for _ in range(H)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(W), "height": str(H)})
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

    add_obj("map_info", "", W // 2, H // 2 - 20, {
        "type": "skirmish",
        "winCondition": "mainBuilings",
        "fog": "los",
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
        add_unit("builder", team, sx - 40, sy)
        add_unit("builder", team, sx, sy + 40)

    for (cc, rr) in CRYSTALS:
        add_unit("crystalResource", -1, cc * 20, rr * 20)

    add_obj("camera_start", "camera_start", W // 2 * 20, H // 2 * 20, {}, 20, 20)

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
    issues = K.validate_tmx(tree, W, H, fgmap, spawns)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, spawns, grid, items, decor, issues


def _layer_ger(root, name, H, W):
    for l in root.findall("layer"):
        if l.get("name") == name:
            raw = base64.b64decode(l.find("data").text.strip())
            buf = gzip.decompress(raw)
            g = struct.unpack("<%dI" % (len(buf) // 4), buf)
            return [[g[r * W + c] for c in range(W)] for r in range(H)]
    return [[0] * W for _ in range(H)]


def render_ger(tmx, out_png, H, W):
    """支持矩形的预览渲染（K.render 假设正方形，这里按 H×W 渲染）。"""
    root = ET.parse(tmx).getroot()
    im = np.array(Image.open(C.PNG).convert("RGBA"))
    cols = C._COLS; TW = TH = 20

    def tile_img(tid):
        r = tid // cols; c = tid % cols
        return im[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :3].copy()

    canvas = np.zeros((H * TH, W * TW, 3), dtype=np.uint8)
    data = _layer_ger(root, "Ground", H, W)
    decor = _layer_ger(root, "Decorations", H, W)
    items = _layer_ger(root, "Items", H, W)
    for r in range(H):
        for c in range(W):
            g = data[r][c]
            if g >= GROUND_FG:
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = tile_img(g - GROUND_FG)
            dg = decor[r][c]
            if dg >= GROUND_FG:
                ov = tile_img(dg - GROUND_FG)
                mask = (ov.sum(2) > 10)
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW][mask] = ov[mask]
            if items[r][c] >= MISC_FG:
                canvas[r * TH + 6:r * TH + 14, c * TW + 6:c * TW + 14] = (255, 210, 0)
    uo = root.find("objectgroup[@name='UnitObjects']")
    if uo is not None:
        for o in uo.findall("object"):
            u = o.find("properties/property[@name='unit']")
            if u is not None and u.get("value") == "crystalResource":
                cc = int(int(o.get("x", 0)) // TW); rr = int(int(o.get("y", 0)) // TH)
                canvas[rr * TH + 4:rr * TH + 16, cc * TW + 4:cc * TW + 16] = (0, 200, 220)
    Image.fromarray(canvas).save(out_png)


def annotate_preview(path="rw_germany_preview.png"):
    """在预览图上标注 8 城出生点、海域、山脉与三大河流，更像"地图"。"""
    im = Image.open(path).convert("RGB")
    Wd, Hd = im.size
    d = ImageDraw.Draw(im)
    TILE = 20
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        f_big = ImageFont.truetype(FONT, 26, index=0)
        f_mid = ImageFont.truetype(FONT, 18, index=0)
    except Exception:
        f_big = f_mid = ImageFont.load_default()
    COL = (225, 45, 45)
    for (name, sr, sc, team) in CITIES:
        cx, cy = sc * TILE, sr * TILE
        r = 26
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=COL, width=5)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=COL)
        d.text((cx + 10, cy - 12), f"{name}", font=f_mid, fill=(255, 255, 255))
    # 海域 / 山脉
    d.text((Wd * 0.28, 18), "北海", font=f_big, fill=(235, 245, 255))
    d.text((Wd * 0.66, 18), "波罗的海", font=f_big, fill=(235, 245, 255))
    d.text((Wd * 0.38, Hd - 30), "阿尔卑斯山", font=f_big, fill=(255, 255, 255))
    # 三大河流
    d.text((Wd * 0.30, Hd * 0.46), "莱茵河", font=f_mid, fill=(20, 90, 200))
    d.text((Wd * 0.50, Hd * 0.36), "易北河", font=f_mid, fill=(20, 90, 200))
    d.text((Wd * 0.58, Hd * 0.80), "多瑙河", font=f_mid, fill=(20, 90, 200))
    im.save(path)


def verify_connectivity(grid, spawns):
    """最严格通行规则：水/海/洋/高石不可通行。返回 (全连通, 各出生点互达数)。"""
    IMPASS = {7, 8, 9, 11, 14}
    import collections
    seen_all = []
    def bfs(sr, sc):
        seen = [[False] * W for _ in range(H)]
        q = collections.deque([(sr, sc)]); seen[sr][sc] = True
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < H and 0 <= cc < W and not seen[rr][cc]:
                    if grid[rr][cc] not in IMPASS:
                        seen[rr][cc] = True; q.append((rr, cc))
        return seen
    results = []
    for i, (sr, sc, _t) in enumerate(spawns):
        reach = bfs(sr, sc)
        cnt = sum(1 for (jr, jc, _j) in spawns if reach[jr][jc])
        results.append(cnt)
    full = all(r == len(spawns) for r in results)
    return full, results


if __name__ == "__main__":
    tree, spawns, grid, items, decor, issues = generate(seed=7, out="rw_germany.tmx")
    render_ger("rw_germany.tmx", "rw_germany_preview.png", H, W)
    annotate_preview("rw_germany_preview.png")
    full, reach = verify_connectivity(grid, spawns)
    nres = sum(sum(row) for row in items)
    print("生成完成: rw_germany.tmx  (%dx%d)" % (W, H))
    print("8 城出生点:", [(n, sr, sc, t) for (n, sr, sc, t) in CITIES])
    print(f"起步矿(res_pool)={nres}  中立水晶(crystalResource)={len(CRYSTALS)}")
    print("连通性(最严格·水/高石不可通行): 全连通={}  各点可达出生点数={}".format(full, reach))
    print("校验 issues:", issues if issues else "无")
