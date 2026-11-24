# -*- coding: utf-8 -*-
"""八张 120×120 原版向竞速图 · V2（特色增强版）

相较第一版的改变（直接回应"太规整/太对称/AI味/缺特色"反馈）：
  1) 自然纹理层 texture_pass（画在最后、只落"5×5 全基面"安全区、调色板为土/石/沙/泥）：
     打破"一整片同色"的扁平感——官方原版"有生活感"的关键，也是消除 AI 味最划算的一招。
     ★ 花屏根因教训：高草只接草/泥/水，绝不接石/沙/土；纹理若画在特征之前、或含高草，
       后续特征一贴上来就形成"草+高草+石"三岔块（本图集只有两类过渡，必花屏）。
  2) 多峰山形 massif：石基底(半径>峰顶外延，石必包住高石) + 高低错落高峰 + 山顶草台。
  3) 非对称有机布局：地形特征全部带随机偏移/摆动，绝不左右镜像；矿坑仍按官方"中心对称散布"。
  4) 每图专属母题记忆点：圣坛平台、河心沙洲群、中央台地、冰川湖群、断裂山脊+关隘、会战高丘、
     十字岩浆湖、伸入湖心的半岛群。
  5) 桥头浅滩：跨水的石桥两端用 SHOAL 做"假水"过渡（陆海军皆可通行），桥面仍是实心石/草；
     浅滩绝不当桥面，也绝不绕湖成环。
  6) 兵种平衡：陆地图广泛撒高草林（挡视野/给陆军掩护）+ 水塘/丘壑（地面隘口），避免开阔平原
     让机甲/空军独大；图六"丘陵会战"以中央会战高丘为焦点。
  7) 圆盘类(湖/池/沙洲/冰川湖)一律用 dilate_halo（以同一形状外扩厚环），杜绝同心双形凸角三岔。

硬标准（全部保留）：120×120；8 家预置 commandCenter；矿坑 12 个中心对称、3×3 九宫格、不挨山/水；
桥=石跨屏障；零花屏；修边≥98%；零断路；容器 C1~C10 PASS。
"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E
import gen_5v5_common as G5
from new_engine import (CV, GRASS, DIRT, STONE, SAND, MUD, SNOW, LAVA,
                        SHOAL, WATER, HIGHGRASS, HIGHSTONE, WAT, BLOCK, fbm, n1)

OUT = "/workspace/重做地图/原版向"


# ============================================================ 通用增强工具
def texture_pass(cv, rng, base, palette, density=0.10, rlo=1.6, rhi=2.6):
    """在 base 地形上撒自然碎斑（土/石/沙/泥，不含高草），打破扁平。

    ★ 安全约束：只落在"5×5 邻域全是 base"的格——保证碎斑外围>=2格仍是基面，
      碎斑(单类)与基面相邻 => 最多 2 类，绝不形成三岔块花屏。
    ★ 必须在所有"大特征之后"调用——大特征已固定，纹理只填开阔地，互不接触。
    palette: [(cat, weight), ...]；blob gap=1 互不重叠。"""
    n = cv.n
    target = int(n * n * density)
    got, tries = 0, 0
    cats = [p[0] for p in palette]
    wts = [p[1] for p in palette]
    span = int(rhi) + 2
    while got < target and tries < target * 150:
        tries += 1
        r = rng.randint(span, n - 1 - span)
        c = rng.randint(span, n - 1 - span)
        if cv.used[r][c]:
            continue
        # 安全约束：5×5 必须全是 base，且不得邻接高石/岩浆/水/高草等"易三色"类，
        # 否则碎斑贴上去就形成 {base, 碎斑, 特征} 三岔花屏。
        safe = True
        for dr in range(-span, span + 1):
            for dc in range(-span, span + 1):
                v = cv.g[r + dr][c + dc]
                if v != base or v in (HIGHSTONE, LAVA, WATER, SHOAL, HIGHGRASS):
                    safe = False
                    break
            if not safe:
                break
        if not safe:
            continue
        rad = rng.uniform(rlo, rhi)
        cat = rng.choices(cats, weights=wts)[0]
        cv.blob(r, c, rad, cat, rng, lobes=rng.randint(5, 8), jit=0.55, gap=1, only={base})
        got += 1
    return got


def jitter_decor(cv, lst, rng, amp=6, lobes=7, jit=0.42):
    """装饰斑块：对固定(近对称)坐标加随机偏移 + 少瓣数有机轮廓，消除 AI 对称感。"""
    for (ry, rx, rad, cat) in lst:
        cv.blob(ry + rng.uniform(-amp, amp), rx + rng.uniform(-amp, amp), rad, cat,
                rng, lobes=lobes, jit=jit)


def dilate_halo(cv, core_cells, width, cat, allow):
    """以同一形状外扩 width 格的 cat 环（只覆盖 allow 中的背景），保证核与背景之间
    恒有 width 格同类的环 => 凸角处也不会出现"核+环+背景"三岔。返回被覆盖的环格。"""
    n = cv.n
    done = []
    for (r, c) in core_cells:
        for dr in range(-width, width + 1):
            for dc in range(-width, width + 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n and cv.g[rr][cc] in allow \
                        and cv.g[rr][cc] != cat:
                    cv.g[rr][cc] = cat
                    done.append((rr, cc))
    return done


def massif(cv, cy, cx, rng, scale, peaks=3, base_cat=STONE, peak_cat=HIGHSTONE,
           jit=0.30, grass_top=True):
    """不规则多峰山：石/雪基底(半径必>峰顶外延，石包住高石) + 高低错落高峰 + 山顶草台。"""
    cv.blob(cy, cx, scale * 1.04, base_cat, rng, lobes=11, jit=jit)
    pos = []
    for k in range(peaks):
        ang = rng.uniform(0, math.tau)
        off = scale * rng.uniform(0.10, 0.32)
        py = cy + off * math.sin(ang)
        px = cx + off * math.cos(ang)
        ps = scale * rng.uniform(0.30, 0.44)
        cv.blob(py, px, ps, peak_cat, rng, lobes=9, jit=jit + 0.10)
        pos.append((py, px))
    if grass_top and pos:
        top = pos[0]
        cv.blob(top[0], top[1], scale * 0.14, GRASS, rng, lobes=7, jit=0.20, only={peak_cat})
    return pos


def bridge_over_water(cv, r0, r1, c0, c1, rng, rough=0.14, seed=0.0, heads=True):
    """跨水的实心石桥（硬标准"桥=石跨屏障"；石↔水/石↔草均合法二色），
    桥头两侧水格转 SHOAL 做"假水"过渡（浅滩只做桥头，绝不当桥面）。"""
    cv.bridge(r0, r1, c0, c1, cat=STONE, rough=rough, seed=seed)
    if not heads:
        return
    vertical = (r1 - r0) >= (c1 - c0)
    if vertical:
        for rr in (r0 - 1, r1 + 1):
            for cc in range(c0, c1 + 1):
                if cv.inb(rr, cc) and cv.g[rr][cc] == WATER:
                    cv.put(rr, cc, SHOAL)
    else:
        for cc in (c0 - 1, c1 + 1):
            for rr in range(r0, r1 + 1):
                if cv.inb(rr, cc) and cv.g[rr][cc] == WATER:
                    cv.put(rr, cc, SHOAL)


def enforce_2type(grid, rounds=600):
    """通用：把每个 >2 类的 2×2 里"少数类"细胞翻成正交邻域多数类，迭代至零花屏。

    ★ 关键：只翻"在该 2×2 中出现 1 次的类别"的格——每次翻动都消除一个三岔，
      且朝着邻域多数收敛，不引入新震荡；hard 保证最终达到 0。"""
    H, W = len(grid), len(grid[0])
    WAT = {7, 8, 9, 23}
    canon = lambda t: 70 if t in WAT else t

    def bad_blocks():
        out = []
        for r in range(H - 1):
            for c in range(W - 1):
                s = {canon(grid[r][c]), canon(grid[r + 1][c]),
                     canon(grid[r][c + 1]), canon(grid[r + 1][c + 1])}
                if len(s) > 2:
                    out.append((r, c))
        return out

    for it in range(rounds):
        bads = bad_blocks()
        if not bads:
            return it
        for (r, c) in bads:
            cells = [(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)]
            cls = [canon(grid[y][x]) for y, x in cells]
            from collections import Counter
            cnt = Counter(cls)
            singles = [i for i, cl in enumerate(cls) if cnt[cl] == 1]
            if not singles:
                singles = [0, 3] if cnt[cls[0]] <= cnt[cls[1]] else [1, 2]
            for i in singles:
                y, x = cells[i]
                neigh = [canon(grid[y + dy][x + dx])
                         for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))
                         if 0 <= y + dy < H and 0 <= x + dx < W]
                if neigh:
                    maj = Counter(neigh).most_common(1)[0][0]
                    val = None
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and canon(grid[yy][xx]) == maj:
                            val = grid[yy][xx]
                            break
                    if val is not None and canon(val) != cls[i]:
                        grid[y][x] = val
    return rounds


def enforce_2type_v2(grid, rounds=2500):
    """收敛型三色消除器（根治 enforce_2type 的边界震荡）。

    核心思想：每个 >2 类的 2×2 必含"核心特征类"或纯装饰类。
      · 含核心(水7/岩浆11/高石14)：保留核心，把同框其余类统一翻成与之合法的单一种
        "环类"——水→草(若已有草否则石)、岩浆→石、高石→石。核心+环恒为合法二色，
        且翻动方向单调（只把非核心翻成环，绝不引入新类），必收敛。
      · 多个核心冲突(如 水+高石 同框)：先把较少的核心翻成石，再按单核心处理。
      · 无核心(纯装饰三色)：每格翻成 5×5 局部众数（标准去噪，收敛）。
    末段兜底：残余块整体翻成块内众数，确保最终 = 0。
    """
    H, W = len(grid), len(grid[0])
    WAT = {7, 8, 9, 23}
    canon = lambda t: 70 if t in WAT else t
    CORE = {7, 11, 14}
    from collections import Counter
    # 推断底色：全图众数；雪原图(众数=雪5)用雪，其余用草。底色与任何地形合法。
    _bgcount = Counter()
    for rr in range(0, H, 4):
        for cc in range(0, W, 4):
            _bgcount[grid[rr][cc]] += 1
    bg = 5 if _bgcount.most_common(1)[0][0] == 5 else 0
    PRIORITY = [0, 5, 2, 1, 3, 4, 12]   # 无核心时的偏好保留顺序（背景/中性优先）

    def ring_of(core, cls):
        if core in (11, 14):
            return 2                       # 岩浆/高石 → 石
        if core == 7:
            return 0 if 0 in cls else 2    # 水 → 草（已有草）/石
        return 0

    def local_majority(r, c):
        cnt = Counter()
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                rr, cc = r + dr, c + dc
                if 0 <= rr < H and 0 <= cc < W:
                    cnt[canon(grid[rr][cc])] += 1
        best, bestv = None, -1
        for cl in PRIORITY:
            v = cnt.get(cl, 0)
            if v > bestv:
                best, bestv = cl, v
        if best is None and cnt:
            best = max(cnt, key=lambda k: cnt[k])
        return best

    def bad_blocks():
        out = []
        for r in range(H - 1):
            for c in range(W - 1):
                s = {canon(grid[r][c]), canon(grid[r + 1][c]),
                     canon(grid[r][c + 1]), canon(grid[r + 1][c + 1])}
                if len(s) > 2:
                    out.append((r, c))
        return out

    for _ in range(rounds):
        bads = bad_blocks()
        if not bads:
            return 0
        targets = {}
        for (r, c) in bads:
            cells = [(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)]
            cls = [canon(grid[y][x]) for y, x in cells]
            cores = {cl for cl in cls if cl in CORE}
            if len(cores) > 1:                 # 多核心冲突：保留较多者，其余翻石
                cnt = Counter(cls)
                keep = max(cores, key=lambda k: cnt[k])
                for i, (y, x) in enumerate(cells):
                    if cls[i] in cores and cls[i] != keep:
                        targets[(y, x)] = 2
                cls = [canon(targets.get((y, x), grid[y][x])) for y, x in cells]
                cores = {cl for cl in cls if cl in CORE}
            if cores:                           # 单核心：其余翻成环类
                core = next(iter(cores))
                ring = ring_of(core, cls)
                for i, (y, x) in enumerate(cells):
                    if cls[i] != core:
                        targets[(y, x)] = ring
            else:                               # 无核心：保留"底色+主装饰类"这组合法二色，
                # 把其余少数装饰类翻回底色（底色与任何地形合法，且不引入新类 → 坏块数严格不增）
                nonbg = [cl for cl in cls if cl != bg]
                if not nonbg:
                    continue
                keep = Counter(nonbg).most_common(1)[0][0]
                for i, (y, x) in enumerate(cells):
                    if cls[i] != bg and cls[i] != keep:
                        targets[(y, x)] = bg
        for (y, x), v in targets.items():
            grid[y][x] = v
    # 兜底：任何残余坏块整块翻成底色（底色与一切合法、且不引入新类 → 严格不增，必归零）
    for _ in range(400):
        bads = bad_blocks()
        if not bads:
            return 0
        for (r, c) in bads:
            for (y, x) in ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)):
                grid[y][x] = bg
    return 0


# ============================================================ 出生点清理
def clear_spawn(cv, sp, rad=5):
    for (sr, sc, _t) in sp:
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if dr * dr + dc * dc > rad * rad:
                    continue
                r, c = sr + dr, sc + dc
                if not cv.inb(r, c):
                    continue
                t = cv.g[r][c]
                if t in (HIGHSTONE, LAVA, WATER, SHOAL):
                    cv.g[r][c] = STONE


def flatten(cv, sp, rad=4):
    for (sr, sc, _t) in sp:
        cv.disc(sr, sc, rad, GRASS if cv.base == GRASS else cv.base)


# ================================================================ 图一 圣坛山
def build_1(n=120):
    """中央圣坛山：石基底 + 多峰 + 山顶石质祭坛平台；3 条加宽盘山道螺旋登顶；
    外围不对称 foothill 丘群。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    cy = cx = (n - 1) / 2.0
    rng = random.Random(1001)

    massif(cv, cy, cx, rng, scale=30, peaks=4, jit=0.34)
    cv.blob(cy, cx, 8.5, STONE, rng, lobes=8, jit=0.22)     # 山顶圣坛平台
    cv.disc(cy, cx, 2.6, STONE)
    cv.put(int(round(cy)), int(round(cx)), STONE)

    for k, ang0 in enumerate((18, 138, 258)):                 # 加宽盘山道（宽 3~4）
        for t in range(0, 110):
            frac = t / 109.0
            rad = 30 - frac * 22
            ang = math.radians(ang0 + frac * 105 + rng.uniform(-6, 6))
            r = cy + rad * math.sin(ang)
            c = cx + rad * math.cos(ang)
            for dr in (-2, -1, 0, 1, 2):
                for dc in (-2, -1, 0, 1, 2):
                    if dr * dr + dc * dc <= 5:
                        cv.put(int(round(r + dr)), int(round(c + dc)), GRASS)
    # 盘山道封边：把紧邻草道的高石降级为石，避免"草+高石+石"三岔
    for r in range(n):
        for c in range(n):
            if cv.g[r][c] == GRASS:
                if any(0 <= r + dr < n and 0 <= c + dc < n and cv.g[r + dr][c + dc] == HIGHSTONE
                       for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < n and 0 <= cc < n and cv.g[rr][cc] == HIGHSTONE:
                            cv.g[rr][cc] = STONE

    for (ry, rx, rad) in [(20, 26, 12), (n - 22, 30, 14), (24, n - 28, 13),
                          (n - 26, n - 30, 11), (58, 18, 9), (62, n - 20, 10)]:
        massif(cv, ry, rx, rng, scale=rad, peaks=rng.randint(1, 2), jit=0.38, grass_top=False)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图二 两岸大河
def build_2(n=120):
    """纵贯大河：河道蜿蜒、宽度随河段变化；3 座非等距石桥（桥头浅滩）；
    河心沙洲群（草核+厚沙环）；凸岸石崖/凹岸沙滩；一条支流汇入。"""
    cv = CV(n, GRASS)
    sp = E.spawns_sides(n)
    rng = random.Random(1002)
    mid = (n - 1) / 2.0

    path = []
    for r in range(n):
        c = mid + n1(r, 2.7, 0.037, 13.0) + 6.0 * fbm(r, mid, 7.1, 0.035, 2) + \
            5.0 * math.sin(r * 0.045 + 1.3)
        path.append((r, c))
    # 大河直接以草岸相接（水↔草合法两两类，无石/沙环 => 无凸角三岔）
    for i in range(len(path) - 1):
        (r0, c0), (r1, c1) = path[i], path[i + 1]
        hw = 9.0 + 4.0 * math.sin(i * 0.06)
        cv.strip([(r0, c0), (r1, c1)], hw, WATER, jitter=3.0, seed=3.3)

    trib = []
    for t in range(40):
        r = 60 + t
        c = path[60][1] - 26 + t * 0.2
        trib.append((r, c))
    cv.strip(trib, 4.5, WATER, jitter=2.0, seed=5.5)

    for k, yr in enumerate((26, 70, 102)):
        c0 = int(round(path[yr][1]))
        bridge_over_water(cv, yr - 2, yr + 2, c0 - 18, c0 + 18, rng, rough=0.16, seed=11.0 + k)

    for (yr, dx, rad) in [(40, 4, 5), (44, 7, 4), (82, -4, 5), (88, 6, 4)]:   # 河中草岛（草↔水合法）+ 洲心沙
        c0 = path[yr][1] + dx
        cells = cv.blob(yr, c0, rad + 3, GRASS, rng, lobes=7, jit=0.4)
        cv.blob(yr, c0, rad, SAND, rng, lobes=6, jit=0.45, only={GRASS})

    for (ry, rx, rad, cat) in [(16, 30, 10, STONE), (n - 18, 28, 11, SAND),
                               (14, n - 34, 9, SAND), (n - 16, n - 32, 10, STONE),
                               (50, 16, 8, MUD), (70, n - 18, 8, MUD)]:
        cv.blob(ry, rx, rad, cat, rng, lobes=9, jit=0.42)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图三 双峡谷
def build_3(n=120):
    """两条平行峡谷（草底 + 断壁高石壁，无石岸）横贯；壁高随段变化、设若干断口；
    中央高地走廊立一座中央台地（争夺焦点）+ 森林；谷间地貌。"""
    cv = CV(n, GRASS)
    sp = [(15, 30, 0), (30, 34, 1), (15, 90, 2), (30, 86, 3),
          (n - 16, 30, 4), (n - 31, 34, 5), (n - 16, 90, 6), (n - 31, 86, 7)]
    rng = random.Random(1003)

    massif(cv, 60, 60, rng, scale=16, peaks=2, jit=0.34, grass_top=False)
    # 中央走廊地貌（高草林 / 泥 / 沙——坐标加随机偏移去对称）
    jitter_decor(cv, [(60, 16, 14, HIGHGRASS), (60, n - 17, 14, HIGHGRASS),
                      (60, 44, 11, MUD), (60, n - 45, 11, MUD),
                      (12, 44, 10, MUD), (108, 44, 10, MUD),
                      (12, n - 45, 10, MUD), (108, n - 45, 10, MUD),
                      (24, 20, 9, SAND), (96, 20, 9, SAND),
                      (24, n - 21, 9, SAND), (96, n - 21, 9, SAND)], rng)

    # 峡谷最后落笔：连续断壁不被台地/装饰覆盖（草底重置谷底 → 断壁画高石）
    for base in (40, 82):
        path = []
        for c in range(n):
            r = base + n1(c, 5.1, 0.043, 7.0) + 3.0 * fbm(base, c, 2.9, 0.04, 2)
            path.append((r, c))
        cv.strip(path, 6.0, GRASS)                          # 草底（无石岸）
        gaps = {c for c in range(n) if rng.random() < 0.07}  # 整列断口（约8个）
        for (r, c) in path:
            if c in gaps:
                continue
            wall = 8 + int(3 * math.sin(c * 0.08 + base))
            for t in range(7, wall + 1):                     # 两侧断壁 → 真峡谷
                for sgn in (1, -1):
                    rr = int(round(r)) + sgn * t
                    cc = int(round(c))
                    if cv.inb(rr, cc):
                        if cv.g[rr][cc] in (HIGHGRASS, MUD, SAND):
                            continue                          # 保留装饰斑块不被石壁吞没
                        cv.put(rr, cc, HIGHSTONE)

    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图四 冰河
def build_4(n=120):
    """雪原冰河：冰河蜿蜒 + 2 座冰桥（桥头浅滩）；不对称雪山 + 冰川湖群(厚石岸) +
    雪地纹理(减弱,岩屑斑)。"""
    cv = CV(n, SNOW)
    sp = E.spawns_sides(n)
    rng = random.Random(1004)
    mid = (n - 1) / 2.0

    path = []
    for r in range(n):
        c = mid + n1(r, 8.3, 0.031, 11.0) + 5.0 * fbm(r, mid, 4.4, 0.03, 2)
        path.append((r, c))
    cv.strip(path, 8.0, WATER, edge=STONE, edge_w=4.0, jitter=2.0, seed=9.1)

    for k, yr in enumerate((36, 82)):
        c0 = int(round(path[yr][1]))
        bridge_over_water(cv, yr - 2, yr + 2, c0 - 16, c0 + 16, rng, rough=0.16, seed=21.0 + k)

    for (ry, rx, rad) in [(14, 26, 13), (n - 15, 32, 11), (20, n - 30, 12),
                          (n - 22, n - 26, 13), (56, 22, 9), (72, n - 26, 10),
                          (40, 44, 8), (86, n - 46, 9)]:
        massif(cv, ry, rx, rng, scale=rad, peaks=rng.randint(1, 3), jit=0.34, grass_top=False)
    for (ry, rx, rad) in [(44, 18, 6), (80, 22, 5), (54, n - 22, 6), (90, n - 18, 7),
                          (30, 60, 5), (n - 32, 64, 5)]:
        cells = cv.blob(ry, rx, rad, WATER, rng, lobes=7, jit=0.30)
        dilate_halo(cv, cells, 5, STONE, {SNOW})
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图五 铁脊
def build_5(n=120):
    """横贯断裂山脊（非"带子"）：起伏石脊 + 高低错落高峰群(各带平滑石质基座) + 脊线外伸支脉 +
    2 处关隘（一宽一窄）；南北地貌。"""
    cv = CV(n, GRASS)
    sp = E.spawns_sides(n)
    rng = random.Random(1005)
    mid = (n - 1) / 2.0

    path = []
    for c in range(n):
        r = mid + n1(c, 6.7, 0.038, 8.0) + 4.0 * fbm(mid, c, 1.7, 0.036, 2) + \
            5.0 * math.sin(c * 0.05)
        path.append((r, c))
    for i in range(len(path) - 1):
        (r0, c0), (r1, c1) = path[i], path[i + 1]
        hw = 11.0 + 3.0 * math.sin(i * 0.05 + 0.7)
        cv.strip([(r0, c0), (r1, c1)], hw, STONE, jitter=4.0, seed=5.5)

    for k in range(7):
        c = rng.randint(8, n - 9)
        rr = path[c][0] + rng.uniform(-2, 2)
        ps = rng.uniform(4, 6)
        cv.blob(rr, c, ps + 6, STONE, rng, lobes=6, jit=0.15)     # 平滑厚石基座
        cv.blob(rr, c, ps, HIGHSTONE, rng, lobes=9, jit=0.42)
        if rng.random() < 0.6:
            cv.blob(rr, c, ps * 0.3, GRASS, rng, lobes=6, jit=0.25, only={HIGHSTONE})

    for _ in range(5):
        cc = rng.randint(12, n - 13)
        rr = path[cc][0]
        dire = 1 if rng.random() < 0.5 else -1
        ln = rng.randint(10, 20)
        for s in range(ln):
            yy = rr + dire * s
            xx = cc + rng.uniform(-1.5, 1.5)
            cv.blob(yy, xx, 3.0, STONE, rng, lobes=7, jit=0.5)
            if s % 4 == 0:
                cv.blob(yy, xx, 2.0, HIGHSTONE, rng, lobes=6, jit=0.5, only={STONE})

    for (gc, gw) in [(42, 13), (84, 6)]:
        for c in range(gc - gw, gc + gw + 1):
            if 0 <= c < n:
                for (r, _cc) in path:
                    if _cc == c:
                        for dr in range(-12, 13):
                            yy = int(round(r)) + dr
                            if cv.inb(yy, c) and cv.g[yy][c] == HIGHSTONE:
                                cv.g[yy][c] = STONE
                        break
    jitter_decor(cv, [
        (20, 24, 17, HIGHGRASS), (n - 21, 24, 17, HIGHGRASS),
        (20, n - 25, 17, HIGHGRASS), (n - 21, n - 25, 17, HIGHGRASS),
        (58, 16, 13, MUD), (62, 16, 13, MUD),
        (58, n - 17, 13, MUD), (62, n - 17, 13, MUD),
        (26, 52, 11, SAND), (94, 52, 11, SAND),
        (26, n - 53, 11, SAND), (94, n - 53, 11, SAND)], rng, amp=8)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图六 丘陵会战
def build_6(n=120):
    """无大屏障的会战图：中央会战高丘为焦点；四周撒低丘（制高点）、高草林（陆军掩护/挡视野）、
    水塘（地面隘口）、泥沼、沙斑。三件套保证机甲/空军不独大。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    rng = random.Random(1006)

    def scatter(count, rad_lo, rad_hi, place, forbid):
        """★ 排除半径必须用"本次实际 rad+边距"，不能用 rad_hi——否则前几种特征
        把地图排除饱和，后面的林/塘全部放不下（图六高草林=0 的根因）。"""
        got, tries = 0, 0
        while got < count and tries < 9000:
            tries += 1
            r = rng.randint(12, n - 13)
            c = rng.randint(12, n - 13)
            rad = rng.randint(rad_lo, rad_hi)
            if any((r - fr) ** 2 + (c - fc) ** 2 < (rad + frad + 2) ** 2
                   for fr, fc, frad in forbid):
                continue
            place(r, c, rad)
            forbid.append((r, c, rad))
            got += 1
        return forbid

    forb = [(sr, sc, 9) for sr, sc, _t in sp]
    massif(cv, (n - 1) / 2.0, (n - 1) / 2.0, rng, scale=18, peaks=3, jit=0.34, grass_top=True)

    def hill(r, c, rad):
        cells = cv.blob(r, c, rad * 0.78, STONE, rng, lobes=10, jit=0.38, gap=1)
        cv.blob(r, c, rad * 0.40, HIGHSTONE, rng, lobes=9, jit=0.42, gap=1, only={STONE})

    def pond(r, c, rad):
        cells = cv.blob(r, c, rad, WATER, rng, lobes=9, jit=0.40)
        dilate_halo(cv, cells, 4, MUD, {GRASS, SAND, DIRT, HIGHGRASS})

    def wood(r, c, rad):
        cv.blob(r, c, rad, HIGHGRASS, rng, lobes=12, jit=0.46, gap=1)

    # ★ 顺序=优先级：高草林(陆军掩护/兵种平衡) > 水塘(地面隘口) > 低丘(制高点)，
    #   保证最重要的特征一定放得下（后放的被饿死是允许的）。
    forb = scatter(8, 9, 15, wood, forb)
    forb = scatter(7, 8, 13, pond, forb)
    forb = scatter(8, 10, 15, hill, forb)

    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图七 十字岩浆（8 家 / 120）
def build_7(n=120):
    """十字形岩浆河 + 中央岩浆湖 + 4 座石桥；四臂岩浆边缘锯齿；象限内零星岩浆池(厚石岸)；
    四角地貌。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    rng = random.Random(1007)
    mid = (n - 1) / 2.0

    vpath = [(r, mid + n1(r, 3.9, 0.033, 5.0)) for r in range(n)]
    hpath = [(mid + n1(c, 7.3, 0.030, 5.0), c) for c in range(n)]
    cv.strip(vpath, 10.0, LAVA, edge=STONE, edge_w=3.5, jitter=5.0, seed=2.0)
    cv.strip(hpath, 10.0, LAVA, edge=STONE, edge_w=3.5, jitter=5.0, seed=4.0)
    cv.disc(mid, mid, 15, LAVA)
    m = int(mid)
    cv.bridge(30, 35, m - 19, m + 19, rough=0.18, seed=31.0)
    cv.bridge(n - 38, n - 33, m - 19, m + 19, rough=0.18, seed=32.0)
    cv.bridge(m - 19, m + 19, 30, 35, rough=0.18, seed=33.0)
    cv.bridge(m - 19, m + 19, n - 38, n - 33, rough=0.18, seed=34.0)

    for (ry, rx, rad) in [(30, 30, 6), (n - 32, 34, 7), (34, n - 32, 6),
                          (n - 30, n - 30, 7), (50, 60, 5), (70, 58, 5)]:
        cells = cv.blob(ry, rx, rad, LAVA, rng, lobes=8, jit=0.5)
        dilate_halo(cv, cells, 3, STONE, {GRASS, SAND, MUD, HIGHGRASS, DIRT})

    jitter_decor(cv, [(22, 22, 9, HIGHGRASS), (22, n - 23, 9, HIGHGRASS),
                      (n - 23, 22, 9, HIGHGRASS), (n - 23, n - 23, 9, HIGHGRASS),
                      (40, 40, 7, MUD), (n - 41, n - 41, 7, MUD),
                      (40, n - 41, 7, MUD), (n - 41, 40, 7, MUD),
                      (60, 20, 6, SAND), (80, n - 21, 6, SAND)], rng, amp=7)
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 图八 中央湖
def build_8(n=120):
    """中央不规则大湖（厚沙滩基座+湖水）+ 伸入湖心的三条明显半岛 + 湖心岛；
    一条石质陆桥连湖心岛（桥头浅滩）；外围地貌。不用浅滩绕湖成环。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    rng = random.Random(1008)
    cy = cx = (n - 1) / 2.0

    R = 34
    cells = cv.blob(cy, cx, R, WATER, rng, lobes=11, jit=0.28)
    dilate_halo(cv, cells, 3, SAND, {GRASS})                     # 厚沙滩环（水与草间恒>=3格沙）

    for ang0 in (25, 150, 275):                                   # 三条明显半岛（宽7、长18，只伸入湖、不贯穿）
        for t in range(0, 18):
            d = R - t * 1.05
            if d <= 12:
                break
            taper = 7.0 * (0.35 + 0.65 * (t / 18.0))
            ang = math.radians(ang0 + rng.uniform(-5, 5))
            rr = cy + d * math.sin(ang)
            cc = cx + d * math.cos(ang)
            cv.blob(rr, cc, taper, GRASS, rng, lobes=6, jit=0.5)

    cv.blob(cy, cx, 7, GRASS, rng, lobes=8, jit=0.3)             # 湖心岛
    bridge_over_water(cv, int(cy) - 7, int(cy) + 7, int(cx) - 2, int(cx) + 2, rng,
                      rough=0.1, seed=40.0)                      # 石质陆桥（宽5）

    jitter_decor(cv, [(16, 22, 17, HIGHGRASS), (16, n - 23, 17, HIGHGRASS),
                      (n - 17, 22, 17, HIGHGRASS), (n - 17, n - 23, 17, HIGHGRASS),
                      (58, 10, 13, MUD), (58, n - 11, 13, MUD),
                      (16, 56, 10, SAND), (n - 17, 56, 10, SAND),
                      (30, 30, 7, STONE), (n - 30, n - 30, 7, STONE)], rng, amp=8)
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 4)
    return cv, sp, 12


# ================================================================ 产出
JOBS = [
    ("图一", build_1, 120, "圣坛山 · 中央圣坛+多峰+加宽盘山道"),
    ("图二", build_2, 120, "两岸 · 蜿蜒大河+3非等距桥+沙洲群"),
    ("图三", build_3, 120, "双峡谷 · 断壁峡谷+中央台地"),
    ("图四", build_4, 120, "冰河 · 雪原+冰桥+雪山+冰川湖群"),
    ("图五", build_5, 120, "铁脊 · 断裂山脊+高峰群+2关隘"),
    ("图六", build_6, 120, "丘陵会战 · 中央高丘+林+水塘+丘壑"),
    ("图七", build_7, 120, "十字岩浆 · 岩浆湖+4桥（8家）"),
    ("图八", build_8, 120, "中央湖 · 三半岛+湖心岛+陆桥"),
]


def one(name, builder, n, desc):
    cv, sp, nmine = builder(n)
    # 自然纹理层（最后画，只落开阔安全区；草图用土/石/沙/泥，雪图用岩屑斑）
    rngt = random.Random((hash(name) & 0xffff) ^ 0x9e37)
    if cv.base == SNOW:
        texture_pass(cv, rngt, SNOW, [(STONE, 6), (MUD, 1)], density=0.05, rlo=2.4, rhi=4.2)
    else:
        texture_pass(cv, rngt, GRASS, [(DIRT, 3), (STONE, 2), (SAND, 1), (MUD, 1)], density=0.10)

    E.connect_all(cv, sp)
    bad, _ = E.bfs_ok(cv.g, sp)
    for _ in range(2):
        try:
            G5.edge_auto_fix(cv.g, threshold=99.5, max_iters=10)
        except RuntimeError:
            pass
        enforce_2type_v2(cv.g)
    try:
        G5.edge_auto_fix(cv.g, threshold=99.0, max_iters=30)
    except RuntimeError:
        pass
    enforce_2type_v2(cv.g)
    flower = E.nf(cv.g)
    rate, iso, c0, dg = E.edge_rate(cv.g)
    rng = random.Random(hash(name) & 0xffff)
    items = E.place_mines(cv, sp, nmine, rng)
    trees, nt = E.place_trees(cv, sp, items, rng, count=28)
    out = os.path.join(OUT, f"{name}.tmx")
    issues = E.write_tmx(cv, items, trees, sp, out)
    nm_ = sum(1 for r in range(n) for c in range(n) if items[r][c] > 0)
    cnt = cv.count()
    tot = n * n
    top = " ".join(f"{E.NM.get(k, k)}{v * 100 // tot}%" for k, v in cnt.most_common(5))
    kinds = sum(1 for k, v in cnt.items() if v > tot * 0.004)
    print(f"[{name}] {desc}: 花屏={flower} 修边{rate:.2f}% 尖刺{iso} 断路={bad} 矿={nm_} 树={nt} 地形={kinds}种 | {top}")
    if issues:
        for it in issues[:3]:
            print("    !", it)
    return dict(name=name, flower=flower, bad=bad, mines=nm_, trees=nt, kinds=kinds,
                rate=rate, n=n, desc=desc)


def main():
    os.makedirs(OUT, exist_ok=True)
    res = [one(*j) for j in JOBS]
    print("\n=== 汇总 ===")
    for r in res:
        ok = "OK " if (r["flower"] == 0 and r["bad"] == 0 and r["rate"] >= 98) else "!! "
        print(f"  {ok}{r['name']} {r['n']}px 花屏{r['flower']:>2} 修边{r['rate']:5.2f}% 断路{r['bad']:>2} "
              f"矿{r['mines']:>2} 树{r['trees']:>2} 地形{r['kinds']}种  {r['desc']}")


if __name__ == "__main__":
    main()
