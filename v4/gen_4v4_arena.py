#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 4V4 左右对抗竞技图《群峰环湖竞技场》(Peaks Around the Lake) V5

相对 V4 的改进（用户追问：湖心岛陆军能否到达）：
- 【海陆桥】V4 的湖心岛是四面深水的孤岛，只有海/空军能到（陆军过不去）。V5 用 shoal 水上桥
  （tsx 自带 `water-bridge` 属性瓦片：陆军可涉 + 海军可过，同一条路双域共用）把湖心岛与左右两岸
  连起来：西桥连左岸→岛、东桥镜像连岛→右岸。按 passability_bridges.md 法则（固定窗口、宽浅滩核、
  最后复涂）施工，并用 BFS 实测 8 出生点互达 + 左→右直穿。
- 中央湖保留上下开阔水面供海军机动，桥只在中轴横带，海陆军双线博弈。
- 【矿点竞争性】V2 只有家门口 2 矿/队。V3 新增 8 个【中立可争夺矿】(res_pool)，分布在环湖岸
  + 中轴，与 16 个起始矿共同构成"扩张即落后/领先"的经济对抗；水晶(高价值)与矿(稳定产出)
  分层布置，资源点密集且对称。
- 【地形更多样】新增 石(2) 岩地斑块（可通行，石↔草/水/高石兼容、渲染安全），并加密森林/泥沼。

设计要点（不变）：
- 【左右对等】地形以中轴(col≈99.5)成对生成后 mirror()，两半布局等价 → 竞技公平。
  ★但渲染层用【原生 autotile】，绝不做复制/翻转镜像 hack（那会把右半贴错成"右半全花"）。
  修边的真标准是【零花屏】：verify_no_flower 检测 >2 种地形的 2×2 块，非 0 直接抛错。
  不强求像素级对称——autotile 平局角点的少量差异是自然且合法的，两半都渲染干净即可。
- 【中央环湖】有机大湖(草→沙→浅滩→水)居中，是 8 队必争的水域要冲。
- 【正确渲染约束】RW 真实 2×2 规则：任一 2×2 块内至多 1 种非草地形 → 不同非草间留 ≥1 格草、
  同类型可实心相连。于是山体/森林/泥沼/土路/石地长成真正可见的实心团块。
- 【山体屏障】四角与中轴散布高石(14, cliff 不可通行)山丘作掩体与制高点。
- 【资源等价】每队 2 起始矿 + 8 中立扩张矿 + 4 中立水晶；左岸偶数 0/2/4/6，右岸奇数 1/3/5/7。
- 【修边=验收】地面层整合.tsx 四角对角线自动拼接 + 2×2 花屏清零。

地形角索引：0草 1土 2石 3沙 4泥 7水 8海 9洋 12高草 14高石 23浅滩
"""
import os, sys, math, struct, base64, gzip, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xml.etree.ElementTree as ET
import numpy as np
import gen_combined as C
import gen_koth as K

GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14

SIZE = 200
LEFT_X, RIGHT_X = 30, 169            # 199-30 = 169，左右对称
SPAWN_YS = [28, 76, 124, 172]        # 4 个出生点行（上下留边）
LAKE_C = (100.0, 99.5)               # 中央大湖中心(行,列)，列 99.5 即中轴
LAKE_R = 37                          # 大湖半径

# --------------------------- 确定性噪声（可复现有机海岸） ---------------------------
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


def build_lake(grid, cy, cx, R, rng, phase, jit=0.05):
    """有机大湖：从湖心向外 = 深水(亮蓝) → 浅水/浅滩(暗蓝,2宽) → 沙滩(米黄,4宽) → 草。

    - 海岸线用低频噪声摆动半径(±jit*R)，摆脱"完美圆"的机械钝感（不是圆规画的）；
    - 各带【径向宽度恒定】(噪声只整体平移 d)，故局部 2×2 内至多 2 类地形，不花屏；
    - 真正的沙滩带(米黄)让"草→沙→水"过渡自然，不再是草直接怼暗蓝浅水。
    """
    H = len(grid); W = len(grid[0])
    amp = jit * R
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cy, c - cx) + amp * _noise(r, c)
            if d <= R:
                grid[r][c] = WATER
            elif d <= R + 2:
                grid[r][c] = SHOAL
            elif d <= R + 6:
                grid[r][c] = SAND


def carve_islands(grid, islands):
    """岛：草(可建) → 环岛沙滩(2宽,米黄) → 浅水/浅滩(2宽) → 深水湖。

    islands: [(cr, cc, r_land, r_shoal), ...]，中心允许半整数列(如 99.5)以保持中轴对称。
    """
    H = len(grid); W = len(grid[0])
    for (cr, cc, r_land, r_shoal) in islands:
        for r in range(H):
            for c in range(W):
                d = math.hypot(r - cr, c - cc)
                if d <= r_land:
                    grid[r][c] = GRASS
                elif d <= r_land + 2:
                    grid[r][c] = SAND
                elif d <= r_land + r_shoal:
                    grid[r][c] = SHOAL


def _clean_water_vertices(grid):
    """清洗水族(水/海/洋/浅滩)2×2 三地形花屏。沙(3)是海滩、不算水族，避免被误吞。"""
    WF = {WATER, SEA, OCEAN, SHOAL}
    H = len(grid); W = len(grid[0])
    from collections import Counter
    changed = True; it = 0
    while changed and it < 12:
        changed = False; it += 1
        for vy in range(H + 1):
            for vx in range(W + 1):
                cells = [(vx + dx, vy + dy) for dy, dx in ((-1, -1), (-1, 0), (0, -1), (0, 0))
                         if 0 <= vx + dx < W and 0 <= vy + dy < H]
                ts = [grid[y][x] for x, y in cells]
                if len(set(ts)) <= 2:
                    continue
                wf = [t for t in ts if t in WF]
                if len(wf) < 2:
                    continue
                wfc = Counter(wf)
                wfmaj = max(wfc, key=lambda k: wfc[k])
                for (x, y) in cells:
                    if grid[y][x] in WF and grid[y][x] != wfmaj:
                        grid[y][x] = wfmaj
                        changed = True
    return it


# --------------------------- V2 核心：正确渲染约束下的实心团块 ---------------------------
def _can_paint(grid, r, c, cat, forbid):
    """RW 真实 2×2 规则：任一 2×2 块至多 1 种非草地形。
    → 落子条件：当前为草、不在 forbid、且周围切比雪夫 1(8 邻)内『不同』非草地形数为 0
      （同类 cat 相邻允许 → 实心团块；不同类被 grass 隔开 ≥1 格）。"""
    H = len(grid); W = len(grid[0])
    if not (0 <= r < H and 0 <= c < W):
        return False
    if forbid[r][c]:
        return False
    if grid[r][c] != GRASS:
        return False
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W:
                v = grid[rr][cc]
                if v != GRASS and v != cat:
                    return False
    return True


def place_blob(grid, forbid, cr, cc, rad, cat, rng, lobes=6, jit=0.18):
    H = len(grid); W = len(grid[0])
    phase = rng.uniform(0, math.tau)
    painted = 0
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cr, c - cc)
            ang = math.atan2(r - cr, c - cc)
            rr = rad * (1 + jit * math.sin(lobes * ang + phase))
            if d <= rr and _can_paint(grid, r, c, cat, forbid):
                grid[r][c] = cat
                painted += 1
    return painted


def get_spawns():
    """左岸偶数 0/2/4/6，右岸奇数 1/3/5/7 → 左右各自成军、正好 4V4。"""
    tl = [0, 2, 4, 6]
    tr = [1, 3, 5, 7]
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, tl)] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, tr)])


# --------------------------- 中立资源节点（陆地可争夺点） ---------------------------
# 仅定义左半(col<=99)，靠 mirror 生成右半；中轴点(col=99)自动生成 col100 镜像。
# 水晶 = 高价值中立资源；扩张矿 = 稳定产出中立资源。均落在陆地、近湖岸/中轴 → 双方必争。
CRYSTAL_LEFT = [(55, 55), (145, 55)]                 # 环湖岸上下两角（mirror 出右半 4 角）
EXPANSION_LEFT = [(70, 50), (129, 50), (42, 99), (158, 99)]  # 环湖岸 2 角 + 中轴上下


def mirror_nodes(nodes):
    out = list(nodes)
    for (r, c) in nodes:
        out.append((r, 199 - c))
    # 中轴点 col=99 的镜像 col=100 位置不同，保留（形成 2 宽中轴节点）
    return out


def build_terrain(seed):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # 1) 中央大湖（有机水域 + 沙滩）
    build_lake(grid, LAKE_C[0], LAKE_C[1], LAKE_R, rng, phase=rng.uniform(0, 6), jit=0.07)

    # 1b) 湖心争夺岛：居中(100,99.5)的圆形草岛 + 浅滩环
    #     → 海/空双方必争的中央中立水晶核心；对称于中轴、2×2 安全（浅滩环宽 4）。
    CENTRAL_ISLAND = (100.0, 99.5, 11, 4)   # cr, cc, r_land, r_shoal
    carve_islands(grid, [CENTRAL_ISLAND])

    # 1c) 岛屿掩码：禁止地形团块 / 出生清场覆盖湖心岛
    island_mask = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if math.hypot(r - 100.0, c - 99.5) <= 11 + 4:
                island_mask[r][c] = 1

    # 1d) 海陆桥窗口：shoal 水上桥（陆军可涉 + 海军可过，海陆皆通，单一路径双域共用）。
    #     西桥连左岸→湖心岛，东桥镜像连湖心岛→右岸。
    BRIDGES = [(95, 105, 48, 90), (95, 105, 109, 151)]   # (r0,r1,c0,c1) 含端点
    bridge_mask = [[0] * W for _ in range(H)]
    for (r0, r1, c0, c1) in BRIDGES:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                bridge_mask[r][c] = 1

    # 2) 清洗湖岸水族顶点（含岛屿浅滩环）
    _clean_water_vertices(grid)

    # 3) forbid 掩码：水族(湖/沙/浅滩) + 出生点 ±3 + 中立资源节点 ±2（地形不覆盖节点）
    forbid = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] in (WATER, SEA, OCEAN, SHOAL, SAND) or bridge_mask[r][c]:
                forbid[r][c] = 1
    # 水族外扩 3 格缓冲：禁止任何非草地貌贴湖/贴岛/贴桥落子，
    # 避免山体等过渡贴图把邻近浅滩角拉进来造成 2×2 花屏。
    buf = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if forbid[r][c]:
                for dr in range(-3, 4):
                    for dc in range(-3, 4):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < H and 0 <= cc < W:
                            buf[rr][cc] = 1
    for r in range(H):
        for c in range(W):
            forbid[r][c] = 1 if (buf[r][c] or island_mask[r][c] or bridge_mask[r][c]) else 0
    spawns = get_spawns()
    for (sr, sc, _t) in spawns:
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W:
                    forbid[r][c] = 1
    for (nr, nc) in mirror_nodes(CRYSTAL_LEFT) + mirror_nodes(EXPANSION_LEFT):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = nr + dr, nc + dc
                if 0 <= r < H and 0 <= c < W:
                    forbid[r][c] = 1

    # 4) 山体屏障（高石=cliff）：四角 + 中轴 + 边缘
    mountain_specs = [
        (18, 18, 10), (18, 78, 9), (181, 18, 10), (181, 78, 9),
        (100, 14, 9), (100, 48, 8),
        (52, 12, 7), (148, 12, 7),
    ]
    for (mr, mc, mr_) in mountain_specs:
        place_blob(grid, forbid, mr, mc, mr_, HIGHSTONE, rng, lobes=7, jit=0.16)

    # 5) 森林（高草）：近基地与中轴，成规模掩护林
    forest_specs = [
        (28, 52, 10), (76, 52, 10), (124, 52, 10), (172, 52, 10),
        (100, 62, 9),
        (52, 80, 8), (148, 80, 8),
        (100, 30, 8), (100, 170, 8),   # 中轴上下新增林带（更多样）
    ]
    for (fr, fc, fr_) in forest_specs:
        place_blob(grid, forbid, fr, fc, fr_, HIGHGRASS, rng, lobes=6, jit=0.18)

    # 6) 泥沼洼地（泥=cliff 低地）：上下中部 + 中轴两侧战术低地
    mud_specs = [
        (52, 26, 10), (148, 26, 10),
        (100, 30, 9), (100, 170, 9),
        (60, 60, 7), (140, 60, 7), (60, 140, 7), (140, 140, 7),  # 新增散点泥沼（更多样）
    ]
    for (mr, mc, mr_) in mud_specs:
        place_blob(grid, forbid, mr, mc, mr_, MUD, rng, lobes=6, jit=0.20)

    # 7) 土路走廊（土）：每基地东侧向湖引导
    dirt_specs = [
        (28, 42, 7), (76, 42, 7), (124, 42, 7), (172, 42, 7),
    ]
    for (dr, dc, dr_) in dirt_specs:
        place_blob(grid, forbid, dr, dc, dr_, DIRT, rng, lobes=4, jit=0.22)

    # 8) 石地斑块（石=可通行岩地，新增多样性）：中野开阔地
    stone_specs = [
        (50, 40, 7), (150, 40, 7), (50, 160, 7), (150, 160, 7),
        (100, 75, 6), (100, 125, 6),
    ]
    for (sr, sc, sr_) in stone_specs:
        place_blob(grid, forbid, sr, sc, sr_, STONE, rng, lobes=5, jit=0.20)

    # 9) 强制镜像对称（左右几何完全等价 → 竞技平衡）
    for r in range(H):
        for c in range(100):
            grid[r][199 - c] = grid[r][c]

    # 9b) 铺设海陆桥（shoal 浅滩）：覆写桥窗内的水/沙/草为浅滩，
    #     连通左岸→湖心岛→右岸。autotile 会在浅滩/水交界编出带 water-bridge 属性的桥面
    #     （陆军可涉、海军可过，同一条路双域共用）。
    # ★ 只把【深水】改成浅滩：桥本质是横跨湖面的"沙洲/浅滩通道"，绝不去覆盖岸边的
    #   沙滩(sand)与草地——否则会在桥槽壁凑出 {草,沙,浅滩} 三类 2×2 花屏。
    #   这样岸线保持自然的 草→沙滩→浅水→深水 剖面，桥只是水面上的浅滩脊，双域共用。
    for (r0, r1, c0, c1) in BRIDGES:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if grid[r][c] in (WATER, SEA, OCEAN):
                    grid[r][c] = SHOAL

    # 10) 保护出生点：菱形草芯清场
    for (sr, sc, _t) in spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 2:
                    if grid[r][c] in (WATER, SEA, OCEAN, SHOAL, HIGHSTONE, MUD, HIGHGRASS, DIRT, STONE, SAND):
                        grid[r][c] = GRASS

    _clean_water_vertices(grid)                # 最终保险（水族 2×2 三地形）
    # 最终对称性兜底：仅保证"地形布局"左右等价（公平），不做任何渲染 hack。
    for r in range(H):
        for c in range(100):
            grid[r][199 - c] = grid[r][c]
    return grid, rng, spawns


def place_home_mines(items, grid, spawns):
    """每队 2 个起步矿(res_pool)，就近螺旋找可建草格。"""
    H = len(grid); W = len(grid[0])
    BAD = (WATER, SEA, OCEAN, SHOAL, HIGHSTONE, MUD, HIGHGRASS, SAND, STONE, DIRT)
    for (sr, sc, _t) in spawns:
        for (dr, dc) in ((-2, -3), (2, 3)):
            tr, tc = sr + dr, sc + dc
            if not (0 <= tr < H and 0 <= tc < W and grid[tr][tc] not in BAD):
                found = None
                for rad in range(1, 7):
                    for dd in ((dr + rad, dc), (dr - rad, dc), (dr, dc + rad), (dr, dc - rad)):
                        r, c = sr + dd[0], sc + dd[1]
                        if 0 <= r < H and 0 <= c < W and grid[r][c] not in BAD:
                            found = (r, c); break
                    if found:
                        break
                if not found:
                    continue
                tr, tc = found
            grid[tr][tc] = GRASS
            items[tr][tc] = 1


def place_node_mines(items, grid, nodes):
    """在中立资源节点处放 res_pool（确保草底、可建）。"""
    for (nr, nc) in nodes:
        if 0 <= nr < SIZE and 0 <= nc < SIZE:
            grid[nr][nc] = GRASS
            items[nr][nc] = 1


def make_decor(grid, rng):
    """装饰层：仅用白名单透明底道具。"""
    H = len(grid); W = len(grid[0])
    decor = [[0] * W for _ in range(H)]
    TREE = [890, 891]
    ROCK = [718, 719, 754]
    GRASS_TUFT = [711, 712, 714, 898]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == HIGHGRASS and rng.random() < 0.38:
                decor[r][c] = 1 + rng.choice(TREE)
    for r in range(H):
        for c in range(W):
            if grid[r][c] == HIGHSTONE and rng.random() < 0.22:
                decor[r][c] = 1 + rng.choice(ROCK)
    for r in range(H):
        for c in range(W):
            if grid[r][c] == GRASS and rng.random() < 0.018:
                decor[r][c] = 1 + rng.choice(GRASS_TUFT)
    # 湖面礁石：深水区散布透明底礁岩(718/719/754)，打破湖面空白、增加层次（仍对称随机）
    for r in range(H):
        for c in range(W):
            if grid[r][c] == WATER and rng.random() < 0.014:
                decor[r][c] = 1 + rng.choice(ROCK)
    return decor


def generate(seed=7, out="4v4_arena.tmx"):
    grid, rng, spawns = build_terrain(seed)
    items = [[0] * SIZE for _ in range(SIZE)]
    place_home_mines(items, grid, spawns)
    place_node_mines(items, grid, mirror_nodes(EXPANSION_LEFT))

    decor = make_decor(grid, rng)

    # 原生 autotile 渲染（不做任何复制/翻转镜像 hack）。
    # 教训：曾经的"复制镜像"会把右半过渡方向整体贴错（右半全花）；"翻转镜像(交换角)"也非
    # 视觉翻转（tsx 交换角≠像素翻转，匹配率仅 0.9%），同样把右半贴错。正确做法是让 autotile
    # 按地形自然渲染，两半各自都干净——修边的真标准是"零花屏"，不是强行对称。
    ground_tid = C.autotile(grid)
    # 硬性自检：只要存在会渲染花屏的 2×2 块（>2 种地形类），一律抛错，绝不发布错图。
    _flower_bad = C.verify_no_flower(grid)
    if _flower_bad:
        raise RuntimeError("修边自检未通过(不可发布): 2×2 花屏块=%d" % _flower_bad)
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
        back = 1 if sc < 100 else -1
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    # 中立水晶：陆地可争夺点（环湖岸 + 中轴），地面/空/海皆可争
    for (cc, rr) in mirror_nodes(CRYSTAL_LEFT):
        add_unit("crystalResource", -1, rr * 20, cc * 20)
    # 湖心争夺核心：中央草岛上一对对称中立水晶（海/空双方必争的"心脏"）
    CENTER_CORE = [(100, 99), (100, 100)]
    for (cc, rr) in CENTER_CORE:
        add_unit("crystalResource", -1, rr * 20, cc * 20)

    add_obj("camera_start", "camera_start", 100 * 20, SIZE // 2 * 20, {}, 20, 20)

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


if __name__ == "__main__":
    import json
    out = "/workspace/4v4_arena.tmx"
    tree, spawns, grid, items, decor, issues = generate(seed=7, out=out)
    K.render(out, "/workspace/4v4_arena_preview.png")

    # 标注版预览
    try:
        from PIL import Image, ImageDraw, ImageFont
        im = Image.open("/workspace/4v4_arena_preview.png").convert("RGB")
        W, H = im.size
        TILE = 20
        FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        try:
            f_big = ImageFont.truetype(FONT, 30, index=0)
            f_mid = ImageFont.truetype(FONT, 22, index=0)
        except Exception:
            f_big = f_mid = ImageFont.load_default()
        LEFT = (225, 45, 45); RIGHT = (40, 130, 235); AXIS = (255, 200, 0); CRY = (0, 200, 220); MINE=(255,210,0)
        d = ImageDraw.Draw(im)
        for (sr, sc, team) in spawns:
            cx, cy = sc * TILE, sr * TILE
            col = LEFT if sc == LEFT_X else RIGHT
            d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], outline=col, width=5)
            d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=col)
            d.text((cx, cy), f"T{team}", font=f_mid, fill=(255, 255, 255), anchor="mm")
        for (cc, rr) in mirror_nodes(CRYSTAL_LEFT):
            d.ellipse([cc * TILE - 9, rr * TILE - 9, cc * TILE + 9, rr * TILE + 9], outline=CRY, width=3)
        # 湖心争夺岛 + 中央水晶核心
        d.ellipse([(99.5 - 11) * TILE, (100 - 11) * TILE, (99.5 + 11) * TILE, (100 + 11) * TILE],
                  outline=(0, 220, 235), width=4)
        for (cc, rr) in [(100, 99), (100, 100)]:
            d.ellipse([cc * TILE - 9, rr * TILE - 9, cc * TILE + 9, rr * TILE + 9], outline=(0, 255, 255), width=4)
        # 海陆桥（西桥连左岸、东桥连右岸，过湖心岛）
        for (r0, r1, c0, c1) in [(95, 105, 48, 90), (95, 105, 109, 151)]:
            d.rectangle([c0 * TILE, r0 * TILE, (c1 + 1) * TILE, (r1 + 1) * TILE], outline=(255, 170, 0), width=3)
        for (nr, nc) in mirror_nodes(EXPANSION_LEFT):
            d.rectangle([nc*TILE-7, nr*TILE-7, nc*TILE+7, nr*TILE+7], outline=MINE, width=3)
        ax = 99.5 * TILE
        y = 0
        while y < H:
            d.line([(ax, y), (ax, min(y + 26, H))], fill=AXIS, width=4)
            y += 46
        lx, ly, lw, lh = 24, 24, 660, 270
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 175))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(im)
        d.ellipse([lx + 18, ly + 26, lx + 58, ly + 66], outline=LEFT, width=5)
        d.text((lx + 72, ly + 44), "左岸 偶数队 0/2/4/6", font=f_big, fill=(255, 255, 255), anchor="lm")
        d.ellipse([lx + 18, ly + 86, lx + 58, ly + 126], outline=RIGHT, width=5)
        d.text((lx + 72, ly + 104), "右岸 奇数队 1/3/5/7", font=f_big, fill=(255, 255, 255), anchor="lm")
        d.line([(lx + 20, ly + 162), (lx + 56, ly + 162)], fill=CRY, width=4)
        d.text((lx + 72, ly + 162), "青/青白圈=中立水晶(陆地+湖心)", font=f_big, fill=(255, 255, 255), anchor="lm")
        d.rectangle([lx + 18, ly + 186, lx + 58, ly + 196], outline=MINE, width=3)
        d.text((lx + 72, ly + 186), "黄框=中立扩张矿(必争)", font=f_big, fill=(255, 255, 255), anchor="lm")
        d.ellipse([lx + 20, ly + 210, lx + 54, ly + 244], outline=(0, 220, 235), width=4)
        d.text((lx + 72, ly + 210), "湖心岛=中央水晶(海空争夺)", font=f_big, fill=(255, 255, 255), anchor="lm")
        d.rectangle([lx + 18, ly + 246, lx + 58, ly + 256], outline=(255, 170, 0), width=3)
        d.text((lx + 72, ly + 246), "橙框=海陆桥(陆军涉+海军过)", font=f_big, fill=(255, 255, 255), anchor="lm")
        im.save("/workspace/4v4_arena_preview.png")
    except Exception as e:
        print("预览标注失败(不影响 tmx):", e)

    nres = sum(sum(row) for row in items)
    ncry = len(mirror_nodes(CRYSTAL_LEFT)) + 2   # + 湖心岛一对对称水晶
    ndecor = sum(1 for row in decor for v in row if v)
    from collections import Counter
    terr = Counter(x for row in grid for x in row)
    nm = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 7: "水", 8: "海", 9: "洋", 12: "高草", 14: "高石", 23: "浅滩"}
    print(f"已生成: {out}  ({SIZE}x{SIZE}, 8 队, seed=7)")
    print("地形分布:", {nm.get(k, k): v for k, v in terr.items() if v > 0})
    print(f"起步矿=16  中立扩张矿={nres-16}  中立矿合计={nres}  中立水晶={ncry}  装饰={ndecor}")
    print("出生点(team,row,col):", [(t, sr, sc) for sr, sc, t in spawns])
    print("校验 issues:", issues)
    json.dump(grid, open("/workspace/_grid_terrain.json", "w"))
