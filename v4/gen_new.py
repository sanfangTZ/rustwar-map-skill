# -*- coding: utf-8 -*-
"""八张原版向竞速图：图一 ~ 图八（120×120，图七 140×140 / 10 家）

分割型 4 张：图二(大河) 图四(冰河) 图七(十字岩浆) 图八(中央湖)
起伏型 4 张：图一(圣坛山) 图三(双峡谷) 图五(铁脊) 图六(丘陵会战)
"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E
import gen_5v5_common as G5
from new_engine import (CV, GRASS, DIRT, STONE, SAND, MUD, SNOW, LAVA,
                        SHOAL, WATER, HIGHGRASS, HIGHSTONE, WAT, BLOCK, fbm, n1)

OUT = "/workspace/重做地图/原版向"


def clear_spawn(cv, sp, rad=5):
    """出生点清出可通行地面（高石→石，岩浆/水→石），不引入新类别。"""
    for (sr, sc, _t) in sp:
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if dr * dr + dc * dc > rad * rad:
                    continue
                r, c = sr + dr, sc + dc
                if not cv.inb(r, c):
                    continue
                t = cv.g[r][c]
                if t in (HIGHSTONE, LAVA, WATER):
                    cv.g[r][c] = STONE


def flatten(cv, sp, rad=3):
    for (sr, sc, _t) in sp:
        cv.disc(sr, sc, rad, GRASS if cv.base == GRASS else cv.base)


# ================================================================ 图一 圣坛山
def build_1(n=120):
    """中央一座不规则大山：山脚草原 → 山腰高石 → 山顶草地平台，3 条盘山道。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    cy = cx = (n - 1) / 2.0
    rng = random.Random(1001)

    # 山体：石基底（外圈）→ 高石主体
    cv.blob(cy, cx, 30, STONE, rng, lobes=9, jit=0.22)
    cv.blob(cy, cx, 25, HIGHSTONE, rng, lobes=9, jit=0.24)
    # 山顶草地平台
    cv.blob(cy, cx, 8.5, GRASS, rng, lobes=8, jit=0.18)
    cv.disc(cy, cx, 2.5, STONE)
    # 3 条盘山道（草，从山脚通到山顶，螺旋切入）
    for k, ang0 in enumerate((20, 140, 260)):
        for t in range(0, 100):
            frac = t / 99.0
            rad = 30 - frac * 21
            ang = math.radians(ang0 + frac * 95)
            r = cy + rad * math.sin(ang)
            c = cx + rad * math.cos(ang)
            for dr in (-1, 0, 1, 2):
                for dc in (-1, 0, 1, 2):
                    cv.put(int(round(r + dr)), int(round(c + dc)), GRASS)
    # 山脚地貌：林、沼、沙
    for (ry, rx, rad, cat) in [
        (16, 22, 17, HIGHGRASS), (n - 17, 22, 17, HIGHGRASS),
        (16, n - 23, 17, HIGHGRASS), (n - 17, n - 23, 17, HIGHGRASS),
        (44, 14, 13, MUD), (n - 45, 14, 13, MUD),
        (44, n - 15, 13, MUD), (n - 45, n - 15, 13, MUD),
        (60, 40, 11, SAND), (n - 61, 40, 11, SAND),
        (60, n - 41, 11, SAND), (n - 61, n - 41, 11, SAND),
    ]:
        cv.blob(ry, rx, rad, cat, rng, lobes=11, jit=0.42, gap=1)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图二 两岸
def build_2(n=120):
    """纵贯大河：河宽随河段变化、河道蜿蜒；石岸；3 座石桥。"""
    cv = CV(n, GRASS)
    sp = E.spawns_sides(n)
    rng = random.Random(1002)
    mid = (n - 1) / 2.0

    path = []
    for r in range(n):
        c = mid + n1(r, 2.7, 0.037, 13.0) + 6.0 * fbm(r, mid, 7.1, 0.035, 2)
        path.append((r, c))
    cv.strip(path, 11.0, WATER, edge=STONE, edge_w=2.0, jitter=3.0, seed=3.3)

    # 3 座石桥（桥面 8 格）
    for k, yr in enumerate((30, 84)):
        c0 = int(round(path[yr][1]))
        cv.bridge(yr - 2, yr + 2, c0 - 17, c0 + 17, rough=0.18, seed=11.0 + k)
    # 河心沙洲
    for yr in (42, 78):
        c0 = path[yr][1]
        cv.blob(yr, c0 + 3, 5, SAND, rng, lobes=7, jit=0.3)
    # 两岸地貌
    for (ry, rx, rad, cat) in [
        (22, 24, 18, HIGHGRASS), (98, 24, 18, HIGHGRASS),
        (22, n - 25, 18, HIGHGRASS), (98, n - 25, 18, HIGHGRASS),
        (60, 16, 14, MUD), (60, n - 17, 14, MUD),
        (14, 44, 11, MUD), (106, 44, 11, MUD),
        (14, n - 45, 11, MUD), (106, n - 45, 11, MUD),
        (40, 40, 9, SAND), (80, n - 41, 9, SAND),
    ]:
        cv.blob(ry, rx, rad, cat, rng, lobes=11, jit=0.42, gap=1)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图三 双峡谷
def build_3(n=120):
    """两条平行峡谷（高石壁夹草底）横贯，中间高地走廊为主战场。"""
    cv = CV(n, GRASS)
    sp = [(15, 30, 0), (30, 34, 1), (15, 90, 2), (30, 86, 3),
          (n - 16, 30, 4), (n - 31, 34, 5), (n - 16, 90, 6), (n - 31, 86, 7)]
    rng = random.Random(1003)

    for base in (40, 82):
        path = []
        for c in range(n):
            r = base + n1(c, 5.1, 0.043, 7.0) + 3.0 * fbm(base, c, 2.9, 0.04, 2)
            path.append((r, c))
        cv.strip(path, 6.0, GRASS, edge=STONE, edge_w=2.0)      # 谷底草 + 石坡
        # 谷壁：在石带外侧再包一层高石
        for (r, c) in path:
            for t in list(range(-10, -7)) + list(range(8, 11)):
                for dd in (-1, 0, 1):
                    cv.put(int(round(r + t)), int(round(c + dd)), HIGHSTONE)
    # 中间高地：据点与林
    for (ry, rx, rad, cat) in [
        (60, 20, 16, HIGHGRASS), (60, n - 21, 16, HIGHGRASS),
        (60, 50, 12, MUD), (60, n - 51, 12, MUD),
        (12, 44, 10, MUD), (108, 44, 10, MUD),
        (12, n - 45, 10, MUD), (108, n - 45, 10, MUD),
        (22, 20, 9, SAND), (98, 20, 9, SAND),
        (22, n - 21, 9, SAND), (98, n - 21, 9, SAND),
    ]:
        cv.blob(ry, rx, rad, cat, rng, lobes=11, jit=0.42, gap=1)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图四 冰河
def build_4(n=120):
    """雪原冰河：河 + 石岸 + 2 座冰桥（石面），雪山与冰川湖点缀。"""
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
        cv.bridge(yr - 2, yr + 2, c0 - 16, c0 + 16, rough=0.18, seed=21.0 + k)

    # 雪山（石→高石）与冰川湖
    for (ry, rx, rad) in [(13, 24, 14), (n - 14, 30, 11),
                          (18, n - 30, 12), (n - 20, n - 24, 13),
                          (56, 22, 9), (70, n - 24, 10)]:
        cv.blob(ry, rx, rad + 5, STONE, rng, lobes=9, jit=0.30)
        cv.blob(ry, rx, rad, HIGHSTONE, rng, lobes=8, jit=0.34)
    for (ry, rx, rad) in [(42, 16, 7), (78, 20, 5),
                          (52, n - 20, 6), (88, n - 17, 7)]:
        cv.blob(ry, rx, rad + 3, STONE, rng, lobes=8, jit=0.26)
        cv.blob(ry, rx, rad, WATER, rng, lobes=7, jit=0.28)
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图五 铁脊
def build_5(n=120):
    """横贯山脉 + 2 处关隘（一宽一窄），南北两块大陆。"""
    cv = CV(n, GRASS)
    sp = E.spawns_sides(n)
    rng = random.Random(1005)
    mid = (n - 1) / 2.0
    GATES = [(34, 11), (88, 6)]        # (列, 半宽)：一宽一窄

    path = []
    for c in range(n):
        r = mid + n1(c, 6.7, 0.038, 8.0) + 4.0 * fbm(mid, c, 1.7, 0.036, 2)
        path.append((r, c))
    cv.strip(path, 9.0, STONE, jitter=4.0, seed=5.5)
    for (r, c) in path:
        for t in list(range(-6, -3)) + list(range(4, 7)):
            for dd in (-1, 0, 1):
                cv.put(int(round(r + t)), int(round(c + dd)), HIGHSTONE)
    # 关隘：整段高石降为石（可通行），不铺草
    for (gc, gw) in GATES:
        for c in range(gc - gw, gc + gw + 1):
            if not (0 <= c < n):
                continue
            for rr in range(n):
                pass
            # 找到该列山脊位置，降级 ±10 行
            for (r, cc) in path:
                if cc == c:
                    for dr in range(-10, 11):
                        rr = int(round(r)) + dr
                        if cv.inb(rr, c) and cv.g[rr][c] == HIGHSTONE:
                            cv.g[rr][c] = STONE
    for (ry, rx, rad, cat) in [
        (20, 24, 17, HIGHGRASS), (n - 21, 24, 17, HIGHGRASS),
        (20, n - 25, 17, HIGHGRASS), (n - 21, n - 25, 17, HIGHGRASS),
        (58, 16, 13, MUD), (62, 16, 13, MUD),
        (58, n - 17, 13, MUD), (62, n - 17, 13, MUD),
        (26, 52, 11, SAND), (94, 52, 11, SAND),
        (26, n - 53, 11, SAND), (94, n - 53, 11, SAND),
    ]:
        cv.blob(ry, rx, rad, cat, rng, lobes=11, jit=0.42, gap=1)
    clear_spawn(cv, sp, 5)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图六 丘陵会战
def build_6(n=120):
    """无大屏障：丘陵、沼泽、林带随机错落，诸兵种公开赛。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    rng = random.Random(1006)

    def scatter(count, rad_lo, rad_hi, place, forbid):
        got, tries = 0, 0
        while got < count and tries < 3000:
            tries += 1
            r = rng.randint(12, n - 13)
            c = rng.randint(12, n - 13)
            if any((r - fr) ** 2 + (c - fc) ** 2 < (rad_hi + frad + 6) ** 2
                   for fr, fc, frad in forbid):
                continue
            rad = rng.randint(rad_lo, rad_hi)
            place(r, c, rad)
            forbid.append((r, c, rad))
            got += 1
        return forbid

    forb = [(sr, sc, 8) for sr, sc, _t in sp]
    # 丘陵（石台 + 高石顶）
    def hill(r, c, rad):
        cv.blob(r, c, rad * 0.78, STONE, rng, lobes=10, jit=0.38, gap=1)
        cv.blob(r, c, rad * 0.40, HIGHSTONE, rng, lobes=9, jit=0.42, gap=1)
    forb = scatter(9, 10, 16, hill, forb)
    # 沼泽（泥 + 水塘）
    def bog(r, c, rad):
        cv.blob(r, c, rad, MUD, rng, lobes=12, jit=0.46, gap=1)
        cv.blob(r, c, rad * 0.42, WATER, rng, lobes=9, jit=0.40, only={MUD})
    forb = scatter(7, 9, 14, bog, forb)
    # 林带
    def wood(r, c, rad):
        cv.blob(r, c, rad, HIGHGRASS, rng, lobes=12, jit=0.46, gap=1)
    forb = scatter(7, 9, 15, wood, forb)
    # 小地形点缀（碎石/沙斑/草簇）—— 让草原不空，也是官方图的共同特征
    def speck(cat, k):
        got, tries = 0, 0
        while got < k and tries < 3000:
            tries += 1
            r = rng.randint(4, n - 5)
            c = rng.randint(4, n - 5)
            if cv.g[r][c] != GRASS:
                continue
            if any((r - fr) ** 2 + (c - fc) ** 2 < (fr2 + 4) ** 2 for fr, fc, fr2 in forb):
                continue
            rad = rng.uniform(1.6, 3.2)
            cv.blob(r, c, rad, cat, rng, lobes=7, jit=0.45, gap=1)
            got += 1
    speck(STONE, 26)
    speck(SAND, 14)
    speck(HIGHGRASS, 20)

    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 图七 十字岩浆（10 家）
def build_7(n=140):
    """十字形岩浆河 + 4 座石桥，四角大陆。"""
    cv = CV(n, GRASS)
    sp = E.spawns10(n)
    rng = random.Random(1007)
    mid = (n - 1) / 2.0

    vpath = [(r, mid + n1(r, 3.9, 0.033, 5.0)) for r in range(n)]
    hpath = [(mid + n1(c, 7.3, 0.030, 5.0), c) for c in range(n)]
    cv.strip(vpath, 11.0, LAVA, edge=STONE, edge_w=2.5)
    cv.strip(hpath, 11.0, LAVA, edge=STONE, edge_w=2.5)
    # 中央交叉处保留岩浆（自然形成十字）
    cv.disc(mid, mid, 14, LAVA)
    # 4 座石桥（十字两轴各 2 座）
    m = int(mid)
    cv.bridge(34, 39, m - 18, m + 18, rough=0.18, seed=31.0)
    cv.bridge(n - 40, n - 35, m - 18, m + 18, rough=0.18, seed=32.0)
    cv.bridge(m - 18, m + 18, 34, 39, rough=0.18, seed=33.0)
    cv.bridge(m - 18, m + 18, n - 40, n - 35, rough=0.18, seed=34.0)

    # 四角地貌
    for (ry, rx, rad, cat) in [(22, 22, 9, HIGHGRASS), (22, n - 23, 9, HIGHGRASS),
                               (n - 23, 22, 9, HIGHGRASS), (n - 23, n - 23, 9, HIGHGRASS),
                               (40, 40, 7, MUD), (n - 41, n - 41, 7, MUD),
                               (40, n - 41, 7, MUD), (n - 41, 40, 7, MUD),
                               (60, 20, 6, SAND), (80, n - 21, 6, SAND)]:
        cv.blob(ry, rx, rad, cat, rng, lobes=7, jit=0.30, gap=1)
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 3)
    return cv, sp, 15


# ================================================================ 图八 中央湖
def build_8(n=120):
    """中央不规则大湖 + 伸入湖中的半岛；四周大陆环湖。"""
    cv = CV(n, GRASS)
    sp = E.spawns_quad(n)
    rng = random.Random(1008)
    cy = cx = (n - 1) / 2.0

    cv.blob(cy, cx, 34, WATER, rng, lobes=10, jit=0.26)
    # 浅滩岸（自然过渡，仅湖缘一圈）
    for r in range(n):
        for c in range(n):
            if cv.g[r][c] == GRASS:
                near = any(cv.inb(r + dr, c + dc) and cv.g[r + dr][c + dc] == WATER
                           for dr in (-1, 0, 1) for dc in (-1, 0, 1))
                if near and rng.random() < 0.55:
                    cv.g[r][c] = SHOAL
    # 三条半岛伸入湖中
    for ang0 in (25, 150, 275):
        for t in range(0, 26):
            ang = math.radians(ang0 + 6)
            rr = cy + (40 - t) * math.sin(ang)
            cc = cx + (40 - t) * math.cos(ang)
            for dr in (-4, -3, -2, -1, 0, 1, 2, 3, 4):
                for dc in (-4, -3, -2, -1, 0, 1, 2, 3, 4):
                    if t < 17 and dr * dr + dc * dc <= 20:
                        cv.put(int(round(rr + dr)), int(round(cc + dc)), GRASS)
    # 湖心小岛
    cv.blob(cy, cx, 6, GRASS, rng, lobes=7, jit=0.25)
    cv.ring_last = None
    # 环湖地貌
    for (ry, rx, rad, cat) in [(16, 22, 17, HIGHGRASS), (16, n - 23, 17, HIGHGRASS),
                               (n - 17, 22, 17, HIGHGRASS), (n - 17, n - 23, 17, HIGHGRASS),
                               (58, 10, 13, MUD), (58, n - 11, 13, MUD),
                               (16, 56, 10, SAND), (n - 17, 56, 10, SAND)]:
        cv.blob(ry, rx, rad, cat, rng, lobes=11, jit=0.42, gap=1)
    clear_spawn(cv, sp, 6)
    flatten(cv, sp, 3)
    return cv, sp, 12


# ================================================================ 产出
JOBS = [
    ("图一", build_1, 120, "圣坛山 · 中央大山+盘山道"),
    ("图二", build_2, 120, "两岸 · 纵贯大河+3桥"),
    ("图三", build_3, 120, "双峡谷 · 平行峡谷+高地走廊"),
    ("图四", build_4, 120, "冰河 · 雪原+2冰桥"),
    ("图五", build_5, 120, "铁脊 · 横贯山脉+2关隘"),
    ("图六", build_6, 120, "丘陵会战 · 无大屏障"),
    ("图七", build_7, 140, "十字岩浆 · 4桥（10家）"),
    ("图八", build_8, 120, "中央湖 · 半岛环湖"),
]


def one(name, builder, n, desc):
    cv, sp, nmine = builder(n)
    E.connect_all(cv, sp)          # 兜底：最小破坏代价打通所有出生点
    bad, _ = E.bfs_ok(cv.g, sp)
    # 去掉 1 格尖刺 / 悬空格（修边毛边），再补花屏，交替两轮
    for _ in range(2):
        try:
            G5.edge_auto_fix(cv.g, threshold=99.5, max_iters=8)
        except RuntimeError:
            pass
        E.repair(cv.g)
    try:
        G5.edge_auto_fix(cv.g, threshold=99.4, max_iters=6)
    except RuntimeError:
        pass
    E.repair(cv.g)
    flower = E.nf(cv.g)
    rate, iso, c0, dg = E.edge_rate(cv.g)
    rng = random.Random(hash(name) & 0xffff)
    items = E.place_mines(cv, sp, nmine, rng)
    trees, nt = E.place_trees(cv, sp, items, rng, count=26 if n < 130 else 30)
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
        ok = "OK " if (r["flower"] == 0 and r["bad"] == 0) else "!! "
        print(f"  {ok}{r['name']} {r['n']}px 花屏{r['flower']:>2} 修边{r['rate']:5.2f}% 断路{r['bad']:>2} "
              f"矿{r['mines']:>2} 树{r['trees']:>2} 地形{r['kinds']}种  {r['desc']}")


if __name__ == "__main__":
    main()
