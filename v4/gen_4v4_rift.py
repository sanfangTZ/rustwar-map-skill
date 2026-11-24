#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""干涸裂谷 · 4V4 左右对抗遭遇战 (Dry Rift Valley) — v2 丰富版

风格（与上一份『铁幕海峡』刻意拉开）：
- 一块完整大陆，中央一条蜿蜒【内陆河谷】，中段拓宽成【湖泊】；
- 中央是【荒漠带】（沙/土/石三层质感 + 绿洲水池），两翼 homeland 是草地；
- 障碍物是散落的【方山/孤峰】(HIGHSTONE 圆形石柱) 作掩体；
- 草地两翼散布【森林/丘陵】(HIGHGRASS) 作掩体；
- 决定性水晶落在【河谷小岛 + 湖泊小岛 + 陆桥】上，需登陆或越桥，空军拿不下。

丰富度 & 修边（本版重点）：
- 荒漠用 沙/土/石 三层噪声质感 + 绿洲水池，不再是单调色块；
- 河谷中段扩成湖泊（海军主战场），沿河散布多座小岛 + 2 处陆军陆桥；
- cleanup() 通用修边：删孤立单格、填单格孔洞、打断"仅对角相连"的连接
  （autotile 四角对角拼接在角点接触时会产生伪影，是'修边没修好'的根因）；
- 装饰：石地上撒岩石(827)、泥坑里撒枯木(935) → 细节更足。

平衡：地形按中轴【镜像对称】布置，左右等价、竞技公平。
纯遭遇战：Triggers 只放 map_info + camera_start。
"""
import os, struct, base64, gzip, random, math
from collections import Counter
import xml.etree.ElementTree as ET
import numpy as np
import gen_combined as C
import gen_koth as K

GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

# 地形角索引（地面层整合.tsx 的 terraintypes）
GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14

SIZE = 180
CENTER = 90
LEFT_X, RIGHT_X = 34, 146           # 出生点列（镜像：90±56），绿地 homeland 内
SPAWN_YS = [34, 76, 118, 160]      # 4 个出生点行
DESERT_HALF = 38                    # 荒漠带半宽（cols 52..128），中央争夺区
RIVER_HALF = 3.2                    # 河谷基准半宽（约 6~7 格水）
RIVER_CAP0, RIVER_CAP1 = 8, 172     # 河谷上下封口：不触顶/底边，边框干净
PAINT = {GRASS, DIRT, SAND, MUD, HIGHGRASS, STONE}


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
    return 0.55 * _vn(r, c, 1 / 26.0) + 0.30 * _vn(r, c, 1 / 13.0) + 0.15 * _vn(r, c, 1 / 6.0)

def river_center(r):
    """河谷中线列坐标：低频缓弯（贴近中轴，对两侧公平）。"""
    return CENTER + 6.0 * math.sin(r * 0.045) + 5.0 * _vn(r * 0.4, 13.0, 1 / 50.0)

def river_half(r):
    """河谷半宽：中段(行~68..112)扩成湖泊。"""
    lake_env = max(0.0, 1.0 - abs(r - 90.0) / 22.0)
    return RIVER_HALF + 7.0 * lake_env


def _blob(grid, cr, cc, rad, cat, rng, lobes=6, jit=0.18, only=None, exclude=None):
    """在 (cr,cc) 处放一团有机圆形地形（随机相位每团只采样一次）。"""
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
                if exclude is not None and grid[r][c] in exclude:
                    continue
                grid[r][c] = cat


def _opening(grid, cat):
    """开运算（腐蚀→膨胀）：清除单格毛刺/孤块，让 cliff/石体边缘圆润干净。"""
    H = len(grid); W = len(grid[0])
    m = [[1 if grid[r][c] == cat else 0 for c in range(W)] for r in range(H)]
    er = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if m[r][c] and all(m[r + dr][c + dc]
                               for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                er[r][c] = 1
    di = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if any(er[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                di[r][c] = 1
    for r in range(H):
        for c in range(W):
            if grid[r][c] == cat and not di[r][c]:
                grid[r][c] = GRASS
            elif di[r][c] and grid[r][c] in PAINT:
                grid[r][c] = cat


def cleanup(grid):
    """通用修边（对所有可绘制地块）：
    ① 删孤立尖刺/填单格孔洞：自身类别在 8 邻域中 <3 时，翻成占多数的邻类；
    ② 打断"仅对角相连"：正交邻无同类、对角有同类时，拉成与占多数正交邻同类
       → 强制 4-连通，消除 autotile 四角在角点接触时的伪影（修边没修好的根因）。
    原地修改（先收集变更再统一应用，避免同轮读脏）；绝不触碰水/浅滩/高石。"""
    H = len(grid); W = len(grid[0])
    ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
    DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))
    for _ in range(2):
        changes = []
        for r in range(1, H - 1):
            for c in range(1, W - 1):
                cat = grid[r][c]
                if cat not in PAINT:
                    continue
                orth = [grid[r + dr][c + dc] for dr, dc in ORTH]
                diag = [grid[r + dr][c + dc] for dr, dc in DIAG]
                cnt = sum(1 for x in orth + diag if x == cat)
                if cnt < 3:
                    dom = Counter(orth + diag).most_common(1)[0][0]
                    if dom in PAINT:
                        changes.append((r, c, dom))
                elif cat not in orth and any(x == cat for x in diag):
                    co = Counter(x for x in orth if x in PAINT)
                    if co:
                        changes.append((r, c, co.most_common(1)[0][0]))
        for (r, c, v) in changes:
            grid[r][c] = v
    return grid


def build_terrain(seed):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # 1) 中央荒漠带（沙/土/石三层质感 + 绿洲）：双频噪声驱动有机波浪边；
    #    距中轴越近越偏沙、外围掺土；石(碎石地)成片点缀；最外缘与草地交融
    for r in range(H):
        edge = DESERT_HALF + 7.0 * _vn(r * 0.35, 77.0, 1 / 28.0) + \
            3.0 * _vn(r * 0.35, 155.0, 1 / 12.0)
        for c in range(W):
            dx = abs(c - CENTER)
            if dx < edge:
                ns = _noise(r + 300, c + 300)
                nd = _noise(r + 500, c + 500)
                if dx < edge - 7:
                    if ns > 0.5:
                        grid[r][c] = STONE      # 碎石地
                    elif nd > 0.10:
                        grid[r][c] = DIRT       # 土坪
                    else:
                        grid[r][c] = SAND       # 沙
                else:
                    grid[r][c] = SAND if nd > 0.25 else GRASS   # 沙草交融的 fringe

    # 2) 绿洲：荒漠里几汪小水池（浅滩环 + 水心），独立水塘=景观点缀
    for (or_, oc) in [(50, 72), (50, 108), (130, 72), (130, 108)]:
        _blob(grid, or_, oc, 3.0, WATER, rng, lobes=6, jit=0.15,
              only=(SAND, DIRT, GRASS, STONE))
        _blob(grid, or_, oc, 4.4, SHOAL, rng, lobes=6, jit=0.15,
              only=(SAND, DIRT, GRASS, STONE, WATER))

    # 3) 河谷（水+浅滩）：低频蜿蜒、中段扩湖、上下封口 → 干净边框；
    #    两岸浅滩过渡（柔和入水边）
    for r in range(RIVER_CAP0, RIVER_CAP1 + 1):
        rc = river_center(r); half = river_half(r)
        for c in range(W):
            d = abs(c - rc)
            if d <= half:
                grid[r][c] = WATER
            elif d <= half + 1.5 and grid[r][c] in PAINT:
                grid[r][c] = SHOAL

    # 4) 河谷小岛 / 湖泊小岛（草核，水晶争夺点）：沿河上中下散布
    island_rows = [16, 38, 162]
    lake_island_rows = [84, 96]
    for ir in island_rows + lake_island_rows:
        ic = int(round(river_center(ir)))
        _blob(grid, ir, ic, 3.0, GRASS, rng, lobes=6, jit=0.12,
              only=(WATER, SHOAL))

    # 5) 陆地桥（陆军咽喉）：固定列窗口的矩形实心草地桥，覆盖河谷/湖泊全宽
    #    （不随河道蜿蜒逐行抖动 → 无锯齿、无断点；核心≥20 列纯草地 interior，
    #     即便边缘过渡贴图被判水也能通过）。3 座：中央湖泊桥 + 上下两处河谷桥。
    BRIDGES = [
        (82, 98, 66, 114),    # 中央湖泊桥（横跨中段拓宽的湖泊）
        (50, 62, 72, 108),    # 上河谷桥
        (118, 130, 72, 108),  # 下河谷桥
    ]

    def _fill_bridges():
        for (r0, r1, c0, c1) in BRIDGES:
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if 0 <= c < W and grid[r][c] in (WATER, SHOAL, GRASS,
                                                      DIRT, SAND, MUD, HIGHGRASS, STONE):
                        grid[r][c] = GRASS
            # 桥面土路中心带（宽 9 列，可通行，作为"路"通道）
            for r in range(r0, r1 + 1):
                for c in range(90 - 4, 90 + 5):
                    if 0 <= c < W:
                        grid[r][c] = DIRT

    _fill_bridges()

    # 6) 方山/孤峰（HIGHSTONE 圆形石柱，cliff 不可通行）：掩体/视野遮挡，
    #    成对镜像、大小不一、散布荒漠带内、远离河谷与出生点
    mesas = [(40, 68, 5.0), (40, 112, 5.0),
             (70, 64, 4.5), (70, 116, 4.5),
             (90, 62, 6.5), (90, 118, 6.5),
             (110, 64, 4.5), (110, 116, 4.5),
             (140, 68, 5.0), (140, 112, 5.0)]
    for (mr, mc, rad) in mesas:
        _blob(grid, mr, mc, rad, HIGHSTONE, rng, lobes=7, jit=0.10,
              only=(GRASS, DIRT, SAND, MUD, HIGHGRASS, STONE))
    _opening(grid, HIGHSTONE)

    # 7) 森林（HIGHGRASS 丛，贴基地与中段的掩体）：成对镜像，落在绿地 homeland
    forests = [(28, 46), (28, 134), (56, 46), (56, 134), (90, 44), (90, 136),
               (124, 46), (124, 134), (152, 46), (152, 134)]
    for (fr, fc) in forests:
        rad = 5.5 if fr in (56, 124) else 4.5
        _blob(grid, fr, fc, rad, HIGHGRASS, rng, lobes=5, jit=0.14, only=(GRASS,))

    # 8) 沼泽（MUD，荒漠渗水坑/湿地，地形 hazard）：成对镜像、保持小
    swamps = [(50, 80), (50, 100), (130, 80), (130, 100),
              (100, 58), (100, 122)]
    for (wr, wc) in swamps:
        _blob(grid, wr, wc, 3.2, MUD, rng, lobes=5, jit=0.18,
              only=(SAND, DIRT, GRASS, STONE))

    # 8.5) 桥面纯度复涂：最后再铺一遍桥，确保不被 6/7/8 步的石/林/沼覆盖，
    #       核心保持纯草地（过关保障）
    _fill_bridges()

    # 9) 通用修边：删尖刺/填孔洞/打断对角孤立 → 所有可绘制地块边缘干净
    cleanup(grid)

    # 10) 高草去碎屑：被石/河切剩的 <10 格连通片回填成草（避免深色悬崖边碎块）
    seen = [[0] * W for _ in range(H)]
    for r0 in range(H):
        for c0 in range(W):
            if grid[r0][c0] == HIGHGRASS and not seen[r0][c0]:
                stack = [(r0, c0)]; seen[r0][c0] = 1; cells = []
                while stack:
                    r, c = stack.pop(); cells.append((r, c))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < H and 0 <= cc < W and \
                                grid[rr][cc] == HIGHGRASS and not seen[rr][cc]:
                            seen[rr][cc] = 1; stack.append((rr, cc))
                if len(cells) < 10:
                    for r, c in cells:
                        grid[r][c] = GRASS
    return grid, rng


def get_spawns():
    """出生点 (行, 列, team)。左岸偶数 0/2/4/6、右岸奇数 1/3/5/7。"""
    tl = [0, 2, 4, 6]
    tr = [1, 3, 5, 7]
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, tl)] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, tr)])


def protect_bases(grid, spawns):
    """主基地草芯：清掉可能盖在基地上的水/石/泥/高草，保证可建。"""
    H = len(grid); W = len(grid[0])
    for (sr, sc, _t) in spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 2:
                    if grid[r][c] in (WATER, SEA, OCEAN, SHOAL, HIGHSTONE,
                                      MUD, HIGHGRASS):
                        grid[r][c] = GRASS


def place_res(items, grid, spawns):
    """每队 2 个起步矿(res_pool)，紧贴主基地草芯（就近找可建格）。"""
    H = len(grid); W = len(grid[0])
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
    """装饰层：石地(STONE)上撒岩石(827)、泥坑(MUD)里撒枯木(935)（透明叠层，增加细节）。
    岩石为红棕，专用于石/沙地面；绝不盖在灰高石(HIGHSTONE)上（会污染灰石）。"""
    H = len(grid); W = len(grid[0])
    decor = [[0] * W for _ in range(W)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == STONE and rng.random() < 0.20:
                decor[r][c] = 1 + 826          # 岩石
            elif grid[r][c] == MUD and rng.random() < 0.14:
                decor[r][c] = 1 + 934          # 枯木
    return decor


def generate(seed=11, out="rw_4v4_rift.tmx"):
    grid, rng = build_terrain(seed)
    spawns = get_spawns()
    protect_bases(grid, spawns)
    items = [[0] * SIZE for _ in range(SIZE)]
    place_res(items, grid, spawns)
    decor = make_decor(grid, rng)

    # 决定性水晶（全在岛/桥，需登陆或越桥，空军拿不下）：
    #   3 座外圈河谷水上孤岛（海军/登陆陆军争夺） + 3 座陆地桥中心（陆军咽喉）= 6
    crystals = []
    for ir in (16, 38, 162):   # 外圈河谷水上孤岛
        crystals.append((int(round(river_center(ir))), ir))
    for rmid in (56, 90, 124):  # 三座陆地桥中心（必争）
        crystals.append((90, rmid))

    ground_tid = C.autotile(grid)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(SIZE)] for r in range(SIZE)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(SIZE)] for r in range(SIZE)]

    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(SIZE), "height": str(SIZE),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())

    def enc(data):
        raw = struct.pack("<%dI" % (SIZE * SIZE), *[data[r][c] for r in range(SIZE) for c in range(SIZE)])
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * SIZE for _ in range(SIZE)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(SIZE), "height": str(SIZE)})
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

    add_obj("map_info", "", SIZE // 2, SIZE // 2 - 20, {
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
        back = -1 if sc < CENTER else 1   # 工程兵放背侧草芯
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    for (cc, rr) in crystals:
        add_unit("crystalResource", -1, cc * 20, rr * 20)

    add_obj("camera_start", "camera_start", CENTER * 20, SIZE // 2 * 20, {}, 20, 20)

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
    issues = K.validate_tmx(tree, SIZE, SIZE, fgmap, spawns)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, spawns, grid, items, decor, issues


def annotate_preview(path="rw_4v4_rift_preview.png"):
    """标注出生点(红=左岸/蓝=右岸)、蜿蜒河谷对抗轴与图例，不改 tmx。"""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    TILE = 20
    spawns = get_spawns()
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        f_big = ImageFont.truetype(FONT, 30, index=0)
        f_mid = ImageFont.truetype(FONT, 22, index=0)
    except Exception:
        f_big = f_mid = ImageFont.load_default()
    LEFT = (225, 45, 45)
    RIGHT = (40, 130, 235)
    AXIS = (255, 200, 0)

    for (sr, sc, team) in spawns:
        cx, cy = sc * TILE, sr * TILE
        col = LEFT if sc == LEFT_X else RIGHT
        r = 30
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=6)
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=col)
        d.text((cx, cy), f"T{team}", font=f_mid, fill=(255, 255, 255), anchor="mm")

    pts = []
    y = 0
    while y < H:
        x = river_center(y / TILE) * TILE
        pts.append((x, y)); y += 8
    for i in range(len(pts) - 1):
        if i % 2 == 0:
            d.line([pts[i], pts[i + 1]], fill=AXIS, width=5)

    lx, ly, lw, lh = 24, 24, 660, 232
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    d.ellipse([lx + 18, ly + 26, lx + 58, ly + 66], outline=LEFT, width=6)
    d.text((lx + 72, ly + 42), "左岸 偶数队 0/2/4/6", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 18, ly + 86, lx + 58, ly + 126], outline=RIGHT, width=6)
    d.text((lx + 72, ly + 102), "右岸 奇数队 1/3/5/7", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.line([(lx + 20, ly + 178), (lx + 56, ly + 178)], fill=AXIS, width=5)
    d.text((lx + 72, ly + 178), "中央裂谷对抗轴（荒漠·河谷·湖泊·陆桥·平衡）",
            font=f_big, fill=(255, 255, 255), anchor="lm")
    im.save(path)


if __name__ == "__main__":
    tree, spawns, grid, items, decor, issues = generate(seed=11, out="rw_4v4_rift.tmx")
    K.render("rw_4v4_rift.tmx", "rw_4v4_rift_preview.png")
    annotate_preview("rw_4v4_rift_preview.png")
    print("生成完成: rw_4v4_rift.tmx")
    print("出生点(team,row,col):", [(t, sr, sc) for sr, sc, t in spawns])
    nres = sum(sum(row) for row in items)
    nrock = sum(sum(1 for v in row if v) for row in decor)
    ncrys = sum(1 for r in tree.iter("object") for p in r.findall("properties/property")
               if p.get("value") == "crystalResource")
    print(f"起步矿(res_pool)={nres}  水晶={ncrys}  装饰(岩石/枯木)={nrock}")
    print("校验:", issues)
