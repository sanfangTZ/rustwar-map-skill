#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁幕海峡 · 4V4 左右对抗遭遇战 (Iron Curtain Strait) — v2 重写

设计目标：
- 纯遭遇战：Triggers 对象组只放 map_info(type=skirmish) + camera_start，
  不写任何 unitDetect/unitAdd/changeCredits 之类的触发器逻辑宾语（无开局文本、无脚本事件）。
- 左右对抗 4v4：RW 多人对局按奇偶分队（偶数一队、奇数一队），
  左岸 = 偶数队 0/2/4/6，右岸 = 奇数队 1/3/5/7 → 左右各自成军、正好 4V4。
- 用『地面层整合.tsx』完整图集做四角对角线自动拼接（gen_combined.autotile），
  并把整套地形词汇用足：草(0)/沙(3)/浅滩(23)/水(7)/海(8)/洋(9) 做平滑海岸环状分层；
  高石(14)=高山(不可通行 cliff) 做天然山脊屏障；泥(4)=洼地 做河谷走廊；土(1)/高草(12) 做点缀。
- 让海陆军主导、空军沦为辅助：
  ① 中央是南北贯通、上下用陆地封口的海上战场（海峡不通到地图上下边缘，边框干净）；
  ② 决定性经济点(水晶 crystalResource)全部落在海上岛屿/浅滩，空军无法占领，
     必须由海军或登陆陆军控制 → 经济命脉不在天空；
  ③ 基地紧贴海岸（海军一开局就卷入），且背靠山脊屏障（地面强攻需走隘口，陆军决战）。
- 不对称但平衡：左右地形镜像互补（山脊/洼地位置不同），资源总量与出生点质量等价。

地形角索引（来自 地面层整合.tsx 的 terraintypes）：
  0草 1土 2石 3沙 4泥 7水 8海 9洋 12高草 14高石(高山/cliff) 23浅滩
"""
import os, struct, base64, gzip, random, math
import xml.etree.ElementTree as ET
import numpy as np
import gen_combined as C
import gen_koth as K

GROUND_FG = K.GROUND_FG
MISC_FG = K.MISC_FG
_RES_POOL_TILE = K._RES_POOL_TILE
MERGED_COUNT = K.MERGED_COUNT

# 地形角索引
GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14

SIZE = 180
# 海区：仅地图中部 y∈[BAND,BAND2] 为海，上下用陆地封口 → 干净边框
BAND, BAND2 = 12, 168
SEA_HALF = 24                       # 海峡半宽系数（中部海峡宽约 48 格，留出 2 座陆军桥 + 中央海军战场）
LEFT_X, RIGHT_X = 34, 146           # 出生点列（紧贴海岸，海军开局卷入）
SPAWN_YS = [34, 76, 118, 160]      # 4 个出生点行（避开上下陆地封口带）
BACK_L, BACK_R = 13, 167            # 后背山脊列（屏护基地后方）
# 跨海陆地桥（陆军咽喉）：4 座矩形实心草地桥，覆盖海峡全宽+缓冲，保证左右可直穿
#   位置刻意错落，让每个出生点都在 1~2 座桥的服务半径内（竞技公平）
BRIDGE_BANDS = [(22, 32), (54, 66), (114, 126), (148, 158)]


# ---------- 确定性噪声（有机海岸线，可复现） ----------
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


def _env(r):
    """海峡纵向包络：0(陆地)→1(全开)→0，椭圆收口 → 两端自然圆尖，不刀切。"""
    t = (r - 90.0) / 82.0
    if abs(t) >= 1.0:
        return 0.0
    return math.sqrt(1.0 - t * t)


def _coastL(r):
    """左岸线列坐标（海峡透镜形左边缘）。"""
    env = _env(r)
    nz = min(1.0, env * 3.0)            # 端部附近压低噪声 → 圆尖平滑
    return 90.0 - SEA_HALF * env - 3.0 * _noise(r, 0.0) * nz


def _coastR(r):
    """右岸线列坐标（不同噪声相位 → 不对称）。"""
    env = _env(r)
    nz = min(1.0, env * 3.0)
    return 90.0 + SEA_HALF * env + 3.0 * _noise(r, 999.0) * nz


def _add_bridges(grid):
    """跨海陆地桥：在每座桥带内填成矩形实心草地（用桥带中行的海岸线定宽，
    覆盖海峡全宽+3 缓冲），核心≥20 列纯草地 interior → 即便边缘过渡贴图被判水也能通过。
    桥面上再铺一条土路(路)中心带，作为明确的陆军通道。"""
    H = len(grid); W = len(grid[0])
    for (r0, r1) in BRIDGE_BANDS:
        rm = (r0 + r1) // 2
        cl = _coastL(rm); cr = _coastR(rm)
        bl = int(min(cl, cr)) - 3
        br = int(max(cl, cr)) + 3
        for r in range(r0, r1 + 1):
            for c in range(bl, br + 1):
                if 0 <= c < W:
                    grid[r][c] = GRASS
        # 土路中心带（宽 8 列，纯陆地、可通行，作为"路"的视觉与逻辑通道）
        for r in range(r0, r1 + 1):
            for c in range(90 - 4, 90 + 5):
                if 0 <= c < W:
                    grid[r][c] = DIRT
        # 桥头两端向内陆延伸一小段土路，连接出生点一侧
        for r in range(r0 - 4, r1 + 5):
            if 0 <= r < H:
                grid[r][90 - 5] = DIRT if grid[r][90 - 5] in (GRASS, DIRT, SAND) else grid[r][90 - 5]
                grid[r][90 + 4] = DIRT if grid[r][90 + 4] in (GRASS, DIRT, SAND) else grid[r][90 + 4]


def build_terrain(seed):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # 1) 海陆大轮廓 + 海岸环状分层（草→沙→浅滩→水→海→洋）
    #    海峡 = 椭圆收口的"透镜形"内海：两端自然收成圆尖（不再刀切直线）
    for r in range(H):
        env = _env(r)
        if env < 0.02:
            continue                        # 整行陆地（含上下封口带）
        cl = _coastL(r); cr = _coastR(r)
        narrow = (cr - cl) < 10            # 端部海宽不足 → 铺沙滩收口，不挤孤立水格
        for c in range(W):
            if c <= cl:
                dl = cl - c                       # 左陆地距岸
                grid[r][c] = GRASS if dl > 6 else (SAND if dl > 3 else SHOAL)
            elif c >= cr:
                dr = c - cr                       # 右陆地距岸
                grid[r][c] = GRASS if dr > 6 else (SAND if dr > 3 else SHOAL)
            else:
                if narrow:
                    grid[r][c] = SAND
                    continue
                ds = min(c - cl, cr - c)          # 距最近岸（海区深度）
                grid[r][c] = (SHOAL if ds <= 2 else WATER if ds <= 5
                              else SEA if ds <= 13 else OCEAN)

    # 1.5) 跨海陆地桥：横跨海峡的矩形实心草地桥（陆军咽喉），保证左右可直穿
    _add_bridges(grid)

    # 2) 后背山脊（高石=高山，cliff 不可通行）：连续距离场一次成型。
    #    脊线只用低频缓弯 + 干净半宽（高频噪声会把山体掐成一节节虚线段
    #    ——'岩石修边没整好'的主因）；两处隘口为陆军走廊。
    def ridge(c0, passes):
        for r in range(10, SIZE - 10):
            if r in passes:
                continue
            spine = c0 + 3.0 * math.sin(r * 0.045) + \
                2.5 * _vn(r * 0.5, c0 * 3.1, 1 / 55.0)
            half = 3.0 + 0.6 * math.sin(r * 0.017 + c0)     # 半宽缓变：2.4~3.6
            for c in range(int(spine - half) - 2, int(spine + half) + 3):
                if abs(c - spine) <= half and 0 <= c < W and \
                        grid[r][c] in (GRASS, DIRT, MUD, HIGHGRASS, SAND):
                    grid[r][c] = HIGHSTONE
    ridge(BACK_L, passes={52, 128})
    ridge(BACK_R, passes={56, 132})

    # 3) 几座独立山峰（覆盖/视觉焦点，cliff 不可通行）— 内陆，远离出生点
    peaks = [(BACK_L + 10, 28), (BACK_L + 10, 44),
             (BACK_R - 10, 136), (BACK_R - 10, 152)]
    for (pr, pc) in peaks:
        _blob(grid, pr, pc, 6.5, HIGHSTONE, rng, lobes=6, jit=0.10,
              only=(GRASS, DIRT, MUD, HIGHGRASS, SAND))

    # 4) 高石修边：开运算（腐蚀去毛刺/孤块 → 膨胀还原轮廓），
    #    山体边缘圆润，单格碎凸消失；随后重开山口隘口（膨胀会挤窄）
    hs = [[1 if grid[r][c] == HIGHSTONE else 0 for c in range(W)] for r in range(H)]
    er = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if hs[r][c] and all(hs[r + dr][c + dc]
                                for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                er[r][c] = 1
    di = [[0] * W for _ in range(H)]
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if any(er[r + dr][c + dc]
                   for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                di[r][c] = 1
    for r in range(H):
        for c in range(W):
            if grid[r][c] == HIGHSTONE and not di[r][c]:
                grid[r][c] = GRASS           # 毛刺/孤块 → 草
            elif di[r][c] and grid[r][c] in (GRASS, DIRT, MUD, HIGHGRASS, SAND):
                grid[r][c] = HIGHSTONE       # 膨胀补回轮廓
    for pr in (52, 128, 56, 132):            # 重开隘口
        for c in range(W):
            if grid[pr][c] == HIGHSTONE:
                grid[pr][c] = GRASS

    # 5) 洼地（泥）：每侧一整片连通的洪泛盆地——大尺度平滑噪声一次成型，
    #    只保留大连通片 + 元胞平滑 3 轮（圆角/去毛刺/填单格孔），
    #    不再是满地乱撒的孤立碎补丁
    sp = get_spawns()
    # 先收集每侧候选格的低频长波噪声值（轮廓波长 40~80 格 → 平滑大曲线），
    # 再按侧取分位数阈值 → 左右泥盆覆盖率一致（竞技平衡）
    cand = {0: [], 1: []}
    vals = {0: [], 1: []}
    for r in range(BAND + 8, BAND2 - 8):
        cl = _coastL(r); cr = _coastR(r)
        for c in range(W):
            if grid[r][c] != GRASS:
                continue
            dist = (cl - c) if c < 90 else (c - cr)   # 距本侧海岸线
            if not (9 <= dist <= 36):
                continue                               # 只铺在离岸 9~36 格的内陆带
            if any((r - sr) ** 2 + (c - sc) ** 2 < 49 for sr, sc, _t in sp):
                continue                # 避开出生点（半径7圆洞,两侧仍可连通绕行）
            side = 0 if c < 90 else 1
            v = 0.65 * _vn(r + 3000, c + 3000, 1 / 42.0) + \
                0.35 * _vn(r + 3000, c + 3000, 1 / 21.0)
            cand[side].append((r, c))
            vals[side].append(v)
    f = [[0] * W for _ in range(H)]
    _k = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0

    def _gblur_axis(a, axis):
        pads = [(0, 0), (0, 0)]
        pads[axis] = (2, 2)
        ap = np.pad(a, pads, mode="edge")
        sl = [slice(None), slice(None)]
        out = np.zeros_like(a)
        for i in range(5):
            sl[axis] = slice(i, i + a.shape[axis])
            out += _k[i] * ap[tuple(sl)]
        return out

    def _mud_side(side, qcov):
        """单侧泥盆流水线：分位数阈值 → 高斯模糊+重阈值（圆滑有机轮廓，
        元胞平滑必然产生 45° 锯齿楼梯）→ 只留最大连通片（多片显得撕裂）。
        返回 (mask, 最终格数)。左右两侧间隔远,模糊不互相耦合。"""
        n = len(vals[side])
        sv = sorted(vals[side])
        t = sv[min(n - 1, int(n * (1.0 - qcov)))]
        fs = [[0] * W for _ in range(H)]
        for (r, c), v in zip(cand[side], vals[side]):
            if v > t:
                fs[r][c] = 1
        m = np.array(fs, dtype=np.float64)
        for _ in range(2):
            m = _gblur_axis(m, 0)
            m = _gblur_axis(m, 1)
        fs = [[int(v) for v in row] for row in (m > 0.46)]
        seen = [[0] * W for _ in range(H)]
        bestc = []
        for r0 in range(H):
            for c0 in range(W):
                if fs[r0][c0] and not seen[r0][c0]:
                    stack = [(r0, c0)]; seen[r0][c0] = 1; cells = []
                    while stack:
                        r, c = stack.pop(); cells.append((r, c))
                        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            rr, cc = r + dr, c + dc
                            if 0 <= rr < H and 0 <= cc < W and \
                                    fs[rr][cc] and not seen[rr][cc]:
                                seen[rr][cc] = 1; stack.append((rr, cc))
                    if len(cells) > len(bestc):
                        bestc = cells
        mask = [[0] * W for _ in range(H)]
        for r, c in bestc:
            if grid[r][c] == GRASS:
                mask[r][c] = 1
        return mask, len(bestc)

    # 泥盆平衡：先探明每侧可达的最大泥盆,取两侧较小者为目标,
    # 再让每侧选最接近该目标的覆盖率 → 左右泥盆面积基本一致
    QCOVS = (0.38, 0.44, 0.50, 0.56, 0.62, 0.68)
    results = {}
    for side in (0, 1):
        results[side] = [_mud_side(side, q) + (q,) for q in QCOVS]
    target = min(max(n for _m, n, _q in results[s]) for s in (0, 1))
    for side in (0, 1):
        best_mask, best_n = None, -1
        for mask, n, q in results[side]:
            if best_n < 0 or abs(n - target) < abs(best_n - target):
                best_mask, best_n = mask, n
        for r in range(H):
            for c in range(W):
                if best_mask[r][c]:
                    f[r][c] = 1
    for r in range(H):
        for c in range(W):
            if f[r][c] and grid[r][c] == GRASS:
                grid[r][c] = MUD


    # 5) 海上岛屿（草核 + 沙环 + 浅滩环 → 三层干净入水过渡），作为争夺目标
    #    注意 _blob 用 (行, 列)；中央列=90，上下中岛在 行40 / 行140
    islands = [(90, 90, 12), (40, 90, 8), (140, 90, 8)]
    for (ir, ic, rad) in islands:
        # 与主海岸完全一致的六层渐变（洋→海→水→浅滩→沙→草），宽度同比缩放
        _blob(grid, ir, ic, rad + 8, SEA, rng, lobes=7, jit=0.08, only=(OCEAN,))
        _blob(grid, ir, ic, rad + 4, WATER, rng, lobes=7, jit=0.08,
              only=(SEA, OCEAN))
        _blob(grid, ir, ic, rad + 1, SHOAL, rng, lobes=7, jit=0.08,
              only=(WATER, SEA, OCEAN, SHOAL))
        _blob(grid, ir, ic, rad - 2, SAND, rng, lobes=7, jit=0.08,
              only=(SHOAL,))
        _blob(grid, ir, ic, rad - 6, GRASS, rng, lobes=7, jit=0.08,
              only=(SAND,))

    # 7) 高草丘陵（陆地视觉层次）：少而大、圆润（小碎块会渲染成一圈难看的深色悬崖边）
    for (hr, hc) in [(66, 26), (124, 44), (66, 154), (124, 136)]:
        if grid[hr][hc] == GRASS:
            _blob(grid, hr, hc, 5, HIGHGRASS, rng, lobes=5, jit=0.10,
                  only=(GRASS,))
    # 高草去碎屑：被山/泥切剩的 <10 格连通片回填成草
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


def _blob(grid, cr, cc, rad, cat, rng, lobes=6, jit=0.18, only=None, exclude=None):
    """在 (cr,cc) 处放一团有机圆形地形。
    关键：随机相位每团只采样一次（旧版写在逐像素循环里 → 圆被噪声撕成锯齿/方角）。"""
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


def get_spawns():
    """出生点 (行, 列, team)。RW 按奇偶数分队：偶数一队、奇数一队，
    左岸全放偶数 0/2/4/6、右岸全放奇数 1/3/5/7 → 左右各自成军、正好 4V4。"""
    tl = [0, 2, 4, 6]
    tr = [1, 3, 5, 7]
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, tl)] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, tr)])


def protect_bases(grid, spawns):
    """主基地草芯：清掉可能盖在基地上的山/水，保证可建。"""
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
    """每队 2 个起步矿(res_pool)，紧贴主基地草芯（就近找可建格，保证每队稳定 2 矿）。"""
    H = len(grid); W = len(grid[0])
    for (sr, sc, _t) in spawns:
        for (dr, dc) in ((-2, -2), (2, 2)):
            tr, tc = sr + dr, sc + dc
            # 目标格若被山/水/泥/高草占据，就近螺旋找一块可建陆地
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
    """装饰层。注意：高石山体自身已有完整石纹，禁止再盖 826 号'岩石'装饰
    （该装饰是红棕色 RGB[129,105,96]，为草地/泥地设计，盖在灰色石山上
    会变成满山红砖杂斑——之前'黑色石头一大坨乱七八糟'的真凶）。"""
    H = len(grid); W = len(grid[0])
    decor = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == MUD and _noise(r + 8000, c - 8000) > 0.5:
                decor[r][c] = 1 + 934          # 枯木（红棕，与泥地同色系，成簇）
    return decor


def generate(seed=7, out="rw_4v4.tmx"):
    grid, rng = build_terrain(seed)
    spawns = get_spawns()
    protect_bases(grid, spawns)
    items = [[0] * SIZE for _ in range(SIZE)]
    place_res(items, grid, spawns)
    decor = make_decor(grid, rng)

    # 决定性水晶：全部落在海上岛屿/浅滩（空军无法占领 → 海军/陆军主导）
    # 中央大岛 3 + 上下中岛各 1 + 海峡腰部 2（中立 team=-1）
    crystals = [(90, 90), (90, 88), (90, 92),
                (90, 40), (90, 140),
                (80, 90), (100, 90)]

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

    # 仅保留遭遇战元数据：无开局文本、无脚本触发器宾语
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
        back = -1 if sc < 90 else 1   # 工程兵放背侧草芯
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    for (cc, rr) in crystals:
        add_unit("crystalResource", -1, cc * 20, rr * 20)

    add_obj("camera_start", "camera_start", 90 * 20, SIZE // 2 * 20, {}, 20, 20)

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


def annotate_preview(path="rw_4v4_preview.png"):
    """仅在预览图上标注出生点(红=左岸/蓝=右岸)、中央对抗轴与图例，不改 tmx。"""
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
    LEFT = (225, 45, 45)        # 左岸红
    RIGHT = (40, 130, 235)      # 右岸蓝
    AXIS = (255, 200, 0)        # 对抗轴黄

    for (sr, sc, team) in spawns:
        cx, cy = sc * TILE, sr * TILE
        col = LEFT if sc == LEFT_X else RIGHT
        r = 30
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=6)
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=col)
        d.text((cx, cy), f"T{team}", font=f_mid, fill=(255, 255, 255), anchor="mm")

    # 中央海峡对抗轴（竖直黄虚线，列90）
    ax = 90 * TILE
    dash, gap = 26, 20
    y = 0
    while y < H:
        d.line([(ax, y), (ax, min(y + dash, H))], fill=AXIS, width=5)
        y += dash + gap

    # 左上角图例（半透明黑底）
    lx, ly, lw, lh = 24, 24, 640, 232
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    d.ellipse([lx + 18, ly + 26, lx + 58, ly + 66], outline=LEFT, width=6)
    d.text((lx + 72, ly + 42), "左岸 偶数队 0/2/4/6", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 18, ly + 86, lx + 58, ly + 126], outline=RIGHT, width=6)
    d.text((lx + 72, ly + 102), "右岸 奇数队 1/3/5/7", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.line([(lx + 20, ly + 178), (lx + 56, ly + 178)], fill=AXIS, width=5)
    d.text((lx + 72, ly + 178), "中央海峡对抗轴（左右各距 56 格·平衡）",
            font=f_big, fill=(255, 255, 255), anchor="lm")
    im.save(path)


if __name__ == "__main__":
    tree, spawns, grid, items, decor, issues = generate(seed=7, out="rw_4v4.tmx")
    K.render("rw_4v4.tmx", "rw_4v4_preview.png")
    annotate_preview("rw_4v4_preview.png")
    print("生成完成: rw_4v4.tmx")
    print("出生点(team,row,col):", [(t, sr, sc) for sr, sc, t in spawns])
    nres = sum(sum(row) for row in items)
    print(f"起步矿(res_pool)={nres}  海峡水晶(crystalResource)=7")
    print("校验:", issues)
