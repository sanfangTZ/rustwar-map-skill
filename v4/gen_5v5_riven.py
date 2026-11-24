#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 5V5 左右对抗竞技图《五脊裂原 / Riven Plateau》 220×220

创意（纯陆地，刻意避开"中湖+陆地"套路）：
- 5V5：左岸 5 队(0/2/4/6/8)，右岸 5 队(1/3/5/7/9)，地形左右镜像平衡。
- 【弓形错落出生点】中路面向前压、边路后撤，左右镜像 → 平衡、且中/边路节奏不同。
- 【五脊五线】4 条带波浪中线与错位缺口的横向高石"断层脊"把地图切成 5 条战线；
  缺口互错 → 能换线包抄、无法凭单点龟缩成持久战。
- 【枢纽盆地】正中央一块开放石台(非湖)，中心一簇高价值水晶 + 一道熔岩裂口作视觉焦点/硬掩体。
- 【矿点竞争】每人仅 1 座安全起步矿；其余收益全压在"中轴前线矿 + 中央水晶"这些
  双方等距的争夺点上 → 不扩张就穷，逼着打。矿不靠后，杜绝龟缩。
- 【修边=零花屏】原生 autotile（绝不 copy/flip 镜像贴图），verify_no_flower 非 0 直接抛错。
地形角索引：0草 1土 2石 3沙 4泥 7水 8海 9洋 11岩浆 12高草 14高石 23浅滩
"""
import os, sys, math, struct, base64, gzip, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xml.etree.ElementTree as ET
import gen_combined as C
import gen_koth as K

GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
LAVA = 11
HIGHGRASS, HIGHSTONE = 12, 14

SIZE = 220
AXIS = (SIZE - 1) / 2.0          # 109.5 中轴
LANE_YS = [22, 66, 110, 154, 198]        # 5 条战线
RIDGE_YS = [44, 88, 132, 176]            # 4 条断层脊
BASIN = (110.0, 110.0, 26)               # 中央枢纽盆地 (cr,cc,R)


# --------------------------- 噪声 ---------------------------
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


# --------------------------- 地形 ---------------------------
def _blob(grid, cr, cc, rad, cat, rng, jit=0.2, lobes=6, only=(GRASS,)):
    """有机团块：仅落 only 指定的地形，且 8 邻不得有"不同"非草地貌（2×2 安全）。"""
    H = len(grid); W = len(grid[0])
    phase = rng.uniform(0, math.tau)
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cr, c - cc)
            ang = math.atan2(r - cr, c - cc)
            rr = rad * (1 + jit * math.sin(lobes * ang + phase))
            if d > rr or grid[r][c] not in only:
                continue
            ok = True
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    a, b = r + dr, c + dc
                    if 0 <= a < H and 0 <= b < W:
                        v = grid[a][b]
                        if v != GRASS and v != cat:
                            ok = False; break
                if not ok:
                    break
            if ok:
                grid[r][c] = cat


def _add_ridge(grid, ry, gaps):
    """E-W 山脉（高石）：厚重、有机波浪中线、带"山峰"鼓包与山口。gaps=[(cx, half_w)...]"""
    H = len(grid); W = len(grid[0])
    for c in range(W):
        if any(abs(c - gx) <= gw for gx, gw in gaps):
            continue
        cy = ry + 4.5 * math.sin(c * 0.04 + ry * 0.5) + 3.0 * _noise(ry * 3.1, c * 1.5)
        half = 6.0 + 3.5 * _noise(ry + 40.0, c * 1.1)          # 6..9.5 半宽（12~19 厚）
        peak = 4.0 * max(0.0, 0.5 * _noise(c * 0.9 + ry, ry * 2.3) + 0.35)  # 山峰加厚
        half += peak
        r0 = max(0, int(cy - half)); r1 = min(H - 1, int(cy + half))
        for r in range(r0, r1 + 1):
            if grid[r][c] == GRASS:
                grid[r][c] = HIGHSTONE


def build_terrain(seed=7):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # 1) 四条山脉，但【只保留两翼】——中间三分之一(竖带 x≈86..134)完全打通，
    #    让 5 条线在中央"汇流"成一个共享战场（早期分线、中期团队混战），不再是 5 个 1v1。
    #    两翼再各留一个错位侧门，供相邻战线绕后包抄（逼玩家分工看侧翼）。
    gap_plan = {
        44:  [(110, 24), (44, 6), (176, 6)],
        88:  [(110, 24), (56, 6), (164, 6)],
        132: [(110, 24), (56, 6), (164, 6)],
        176: [(110, 24), (44, 6), (176, 6)],
    }
    for ry in RIDGE_YS:
        _add_ridge(grid, ry, gap_plan[ry])

    # 2) 中央石台竞技场：内圈石地(快节奏载具战) + 外圈草地缓冲(隔开山脚，避免"高石/石/草"三类花屏)
    bcr, bcc, bR = BASIN
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - bcr, c - bcc)
            if d <= 20:
                grid[r][c] = STONE
            elif d <= bR:
                grid[r][c] = GRASS

    # 3) 中央熔核：石台正中一小块不规则熔岩（视觉焦点 + 硬掩体），水晶环列石台外圈
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - bcr, c - bcc)
            lim = 4.5 + 2.5 * _noise(r * 1.7 + 3, c * 1.7 - 5)
            if d <= lim:
                grid[r][c] = LAVA

    # 4) 主题战线：外路(线0/4)成片密林、内路(线1/3)成片荒原泥沼、中路(线2)留开放走廊。
    #    按噪声成片（自然边界），山脚留 1 格草缓冲，避免"高石/异类/草"三类 2×2 花屏。
    def near_hs(r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if 0 <= r + dr < H and 0 <= c + dc < W and grid[r + dr][c + dc] == HIGHSTONE:
                    return True
        return False

    for r in range(H):
        for c in range(W):
            if grid[r][c] != GRASS or near_hs(r, c):
                continue
            if abs(c - 110) <= 28:       # 中央汇流带整片留草：共享竞技场保持干净，且隔开两翼森林/泥沼
                continue
            lane = min(range(5), key=lambda i: abs(r - LANE_YS[i]))
            if lane in (0, 4):       # 外路：密林
                if _noise(r * 1.15 + 50, c * 1.15) > 0.12:
                    grid[r][c] = HIGHGRASS
            elif lane in (1, 3):     # 内路：荒原泥沼
                if _noise(r * 1.15 + 130, c * 1.15 + 40) > 0.10:
                    grid[r][c] = MUD

    # 5) 石地高台：中路盆地东西两侧的可通行岩地（增层次）
    for (sr, sc, sr_) in [(110, 68, 7), (110, 151, 7)]:
        _blob(grid, sr, sc, sr_, STONE, rng, lobes=5, jit=0.16)

    # 6) 左右镜像（地形布局等价 → 竞技平衡）
    for r in range(H):
        for c in range(110):
            grid[r][SIZE - 1 - c] = grid[r][c]

    # 7) 出生点弓形错落（中路前压、边路后撤），左右镜像
    left = [(22, 28), (66, 32), (110, 36), (154, 32), (198, 28)]
    spawns = [(y, x, t) for (y, x), t in zip(left, [0, 2, 4, 6, 8])]
    spawns += [(y, SIZE - 1 - x, t) for (y, x), t in zip(left, [1, 3, 5, 7, 9])]

    # 8) 出生点清场（菱形草芯，可建）
    for (sr, sc, _t) in spawns:
        for dr in range(-4, 5):
            for dc in range(-4, 5):
                if abs(dr) + abs(dc) <= 4:
                    r, c = sr + dr, sc + dc
                    if 0 <= r < H and 0 <= c < W:
                        grid[r][c] = GRASS

    return grid, rng, spawns


# --------------------------- 资源 ---------------------------
def _find_grass_near(grid, r, c, rad=6):
    H = len(grid); W = len(grid[0])
    for dd in range(0, rad + 1):
        for dr in range(-dd, dd + 1):
            for dc in range(-dd, dd + 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < H and 0 <= cc < W and grid[rr][cc] == GRASS:
                    return rr, cc
    return None


def place_resources(items, grid, spawns):
    """经济=配合的引擎：
    - 每人 1 座安全起步矿（靠自方后侧）→ 能起步，但仅够起步；
    - 其余全部中立富矿(4 对角矿 + 4 水晶)压在中央共享竞技场 → 一个人吃不下、必须组团抢；
    - 没有"安全后排矿"，想稳经济就得守住并扩大中央 → 不扩张就穷，逼你去打。"""
    H = len(grid); W = len(grid[0])
    # 起步矿：左队放 spawn 西侧(背后)，右队放东侧
    for (sr, sc, team) in spawns:
        back = -1 if sc < AXIS else 1
        loc = None
        for rad in range(4, 12):
            cand = [(sr, sc + back * rad), (sr + 5, sc + back * rad), (sr - 5, sc + back * rad)]
            for (rr, cc) in cand:
                if 0 <= rr < H and 0 <= cc < W and grid[rr][cc] == GRASS:
                    loc = (rr, cc); break
            if loc:
                break
        if loc:
            grid[loc[0]][loc[1]] = GRASS
            items[loc[0]][loc[1]] = 1

    # 中央共享富矿（对角，石台外圈草缓冲带）：4 座，左右/上下对称。
    # 全部中立矿都压在中央共享竞技场——一个人吃不下、必须组团抢，且没有"安全后排矿"可龟。
    for (r, c) in [(93, 93), (93, 126), (127, 93), (127, 126)]:
        g = _find_grass_near(grid, r, c, 4)
        if g:
            grid[g[0]][g[1]] = GRASS
            items[g[0]][g[1]] = 1


# --------------------------- 装饰 ---------------------------
def make_decor(grid, rng):
    H = len(grid); W = len(grid[0])
    decor = [[0] * W for _ in range(H)]
    TREE = [890, 891]
    ROCK = [718, 719, 754]
    TUFT = [711, 712, 714, 898]
    for r in range(H):
        for c in range(W):
            t = grid[r][c]
            if t == HIGHGRASS and rng.random() < 0.36:
                decor[r][c] = 1 + rng.choice(TREE)
            elif t == STONE and rng.random() < 0.10:
                decor[r][c] = 1 + rng.choice(ROCK)   # 只撒石地，高石不撒（避免红砖杂斑）
            elif t == GRASS and rng.random() < 0.012:
                decor[r][c] = 1 + rng.choice(TUFT)
    return decor


# --------------------------- TMX ---------------------------
def generate(seed=7, out="5v5_riven.tmx"):
    grid, rng, spawns = build_terrain(seed)
    items = [[0] * SIZE for _ in range(SIZE)]
    place_resources(items, grid, spawns)
    decor = make_decor(grid, rng)

    # 修边硬门槛：零花屏（不强制对称，只保证渲染干净）
    fb = C.verify_no_flower(grid)
    if fb:
        raise RuntimeError("修边自检未通过(不可发布): 2×2 花屏块=%d" % fb)

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
        "type": "skirmish", "winCondition": "mainBuilings", "fog": "los",
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
        back = 1 if sc < AXIS else -1
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    # 中央高价值水晶（对称 4 颗，避熔岩斜裂）
    for (cr, cc) in [(110, 87), (110, 132), (87, 110), (132, 110)]:
        add_unit("crystalResource", -1, cc * 20, cr * 20)

    add_obj("camera_start", "camera_start", SIZE // 2 * 20, SIZE // 2 * 20, {}, 20, 20)

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


def _annotate(png_out, png_in, spawns):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(png_in).convert("RGB")
    W, H = im.size; TILE = 20
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        f_big = ImageFont.truetype(FONT, 30, index=0)
        f_mid = ImageFont.truetype(FONT, 22, index=0)
    except Exception:
        f_big = f_mid = ImageFont.load_default()
    LEFT = (225, 45, 45); RIGHT = (40, 130, 235); AXISC = (255, 200, 0)
    CRY = (0, 220, 235); MINE = (255, 210, 0)
    d = ImageDraw.Draw(im)
    for (sr, sc, team) in spawns:
        cx, cy = sc * TILE, sr * TILE
        col = LEFT if sc < AXIS else RIGHT
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=col, width=5)
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=col)
        d.text((cx, cy), "T%d" % team, font=f_mid, fill=(255, 255, 255), anchor="mm")
    for (cr, cc) in [(110, 87), (110, 132), (87, 110), (132, 110)]:
        d.ellipse([cc * TILE - 11, cr * TILE - 11, cc * TILE + 11, cr * TILE + 11], outline=CRY, width=4)
    # 盆地
    bcr, bcc, bR = BASIN
    d.ellipse([(bcc - bR) * TILE, (bcr - bR) * TILE, (bcc + bR) * TILE, (bcr + bR) * TILE],
              outline=(120, 220, 140), width=3)
    # 熔岩裂口
    for t in range(-7, 8):
        d.point([(110 + t) * TILE, (110 + t) * TILE], fill=(255, 90, 40))
    # 中轴
    ax = AXIS * TILE; y = 0
    while y < H:
        d.line([(ax, y), (ax, min(y + 24, H))], fill=AXISC, width=3); y += 44
    # 图例
    lx, ly, lw, lh = 24, 24, 700, 175
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    d.ellipse([lx + 18, ly + 26, lx + 58, ly + 66], outline=LEFT, width=5)
    d.text((lx + 72, ly + 44), "左岸 偶数队 0/2/4/6/8", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 18, ly + 86, lx + 58, ly + 126], outline=RIGHT, width=5)
    d.text((lx + 72, ly + 104), "右岸 奇数队 1/3/5/7/9", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 26, ly + 146, lx + 50, ly + 170], outline=CRY, width=4)
    d.text((lx + 72, ly + 148), "青圈=中央高价值水晶 / 绿圈=枢纽盆地 / 橙点=熔岩裂口",
           font=f_mid, fill=(255, 255, 255), anchor="lm")
    im.save(png_out)


if __name__ == "__main__":
    out = "/workspace/5v5_riven.tmx"
    png = "/workspace/5v5_riven_preview.png"
    tree, spawns, grid, items, decor, issues = generate(seed=7, out=out)
    K.render(out, "/workspace/_5v5_raw.png")
    _annotate(png, "/workspace/_5v5_raw.png", spawns)
    print("已生成:", out)

    from collections import Counter
    nm = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 7: "水", 8: "海", 9: "洋", 11: "岩浆", 12: "高草", 14: "高石", 23: "浅滩"}
    print("地形分布:", {nm[k]: v for k, v in Counter(x for row in grid for x in row).items()})
    print("花屏:", C.verify_no_flower(grid), "| 校验 issues:", issues)
    print("出生点:", [(t, r, c) for (r, c, t) in spawns])
    print("起步+前线矿(Items):", sum(1 for row in items for x in row if x), "| 中央水晶:4")
