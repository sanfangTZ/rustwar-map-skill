# -*- coding: utf-8 -*-
"""八张纯地形竞技图 · v3
铁律：
  1) 任意 2×2 ≤ 2 类（水族归一）——几何构造保证。
  2) 墙体剖面：草 | 石 | 高石 | 石 | 草；门只切「石」，门侧 ≥3 格内不放高石（倒角）。
  3) 点状斑块画完立即隔离；出生点 14 格内不许有斑块。
"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import final_engine as E
import gen_5v5_common as G5
import gen_combined as C
from final_engine import (CV, GRASS, DIRT, STONE, SAND, MUD, SNOW, SHOAL, WATER,
                          HIGHGRASS, HIGHSTONE, WAT)

OUT = "/workspace/重做地图/终版"


# ================================================================ 原语
def spoke(cv, cy, cx, r0, r1, ang_deg, halfw, cat, only=None):
    a0 = math.radians(ang_deg)
    n = cv.n
    for r in range(max(0, int(cy - r1 - 2)), min(n, int(cy + r1 + 3))):
        for c in range(max(0, int(cx - r1 - 2)), min(n, int(cx + r1 + 3))):
            dy, dx = r - cy, c - cx
            d = math.hypot(dy, dx)
            if not (r0 <= d <= r1):
                continue
            if only is not None and cv.g[r][c] not in only:
                continue
            if abs(d * math.sin(math.atan2(dy, dx) - a0)) <= halfw:
                cv.g[r][c] = cat


def n1(r, seed, f, amp):
    return amp * (math.sin(r * f + seed) * 0.62 + math.sin(r * f * 2.37 + seed * 1.71) * 0.38)


def patch(cv, cy, cx, rad, cat, rng, lobes=8, jit=0.28, squash=1.0, only=None):
    cells = cv.blob(cy, cx, rad, cat, rng, lobes=lobes, jit=jit, squash=squash,
                    only=only, blk_ok=True)
    for r, c in cells:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if cv.inb(rr, cc):
                    cv.blk[rr][cc] = 1
    return cells


def wall_h(cv, ridge_f, hs, hh, gates, gate_half=11, gm=12):
    n = cv.n
    in_gate = lambda c: any(abs(c - gc) <= gate_half for gc in gates)
    near_gate = lambda c: any(abs(c - gc) <= gate_half + gm for gc in gates)
    for c in range(n):
        if in_gate(c):
            continue
        rg = int(round(ridge_f(c)))
        for dr in range(-hs, hs + 1):
            r = rg + dr
            if 0 <= r < n:
                cv.g[r][c] = STONE
    for c in range(n):
        if near_gate(c):
            continue
        rg = int(round(ridge_f(c)))
        for dr in range(-hh, hh + 1):
            r = rg + dr
            if 0 <= r < n:
                cv.g[r][c] = HIGHSTONE


def ring_wall(cv, cy, cx, rad, hs, hh, gates, gm_deg=9):
    cv.ring(cy, cx, rad - hs, rad + hs, STONE, gates=gates)
    cv.ring(cy, cx, rad - hh, rad + hh, HIGHSTONE, gates=[(a, w + gm_deg) for a, w in gates])


def finish(cv, sp, rad=6):
    E.clear_ground(cv, sp, rad)
    cv.snap_mirror()


# ================================================================ 图一 环渊圣坛
def build_ring(n=200):
    cv = CV(n, GRASS)
    sp = E.spawns8(n)
    cy = cx = (n - 1) / 2.0
    R_ISLE, R_BI, R_BO, R_SHORE = 14.0, 27.0, 30.5, 41.0
    for r in range(n):
        for c in range(n):
            if math.hypot(r - cy, c - cx) <= R_SHORE + 2:
                cv.g[r][c] = WATER
    cv.disc(cy, cx, R_ISLE, GRASS)
    cv.disc(cy, cx, 4.4, STONE)
    cv.ring(cy, cx, 6.0, 7.6, HIGHSTONE)
    cv.ring(cy, cx, R_BI, R_BO, GRASS, gates=[(a, 13) for a in (45, 135, 225, 315)])
    for a in (45, 135, 225, 315):
        spoke(cv, cy, cx, R_BI + 1.1, R_BO - 1.1, a, 1.25, STONE)
    cv.ring(cy, cx, R_SHORE - 3.0, R_SHORE + 1.5, SHOAL)
    for a in (45, 135, 225, 315):
        spoke(cv, cy, cx, R_ISLE - 1, R_SHORE + 1, a, 2.2, SHOAL, only=WAT)
    for a in (0, 90, 180, 270):
        ra = math.radians(a)
        rr = (R_BO + R_SHORE) / 2
        ir, ic = cy + rr * math.sin(ra), cx + rr * math.cos(ra)
        cv.disc(ir, ic, 3.4, GRASS)
        cv.ring(ir, ic, 3.4, 5.2, SHOAL)
    E.protect(cv, sp, 13)
    cv.mark(gap=1)
    rng = random.Random(101)
    for (ry, rx, rad, cat) in [
        (18, 46, 11, HIGHSTONE), (182, 46, 11, HIGHSTONE),
        (18, 154, 11, HIGHSTONE), (182, 154, 11, HIGHSTONE),
        (100, 12, 10, HIGHSTONE), (100, 188, 10, HIGHSTONE),
        (46, 66, 9, HIGHGRASS), (154, 66, 9, HIGHGRASS),
        (46, 134, 9, HIGHGRASS), (154, 134, 9, HIGHGRASS),
        (74, 22, 8, HIGHGRASS), (126, 22, 8, HIGHGRASS),
        (74, 178, 8, HIGHGRASS), (126, 178, 8, HIGHGRASS),
        (100, 58, 6, STONE), (100, 142, 6, STONE),
        (10, 100, 7, STONE), (190, 100, 7, STONE),
        (30, 26, 6, MUD), (170, 26, 6, MUD),
        (30, 174, 6, MUD), (170, 174, 6, MUD),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.30)
    finish(cv, sp)
    return cv, sp, [(int(cy), int(cx)), (int(cy - 27), int(cx - 27)), (int(cy + 27), int(cx - 27))]


# ================================================================ 图二 长湖映月
def build_longlake(n=200):
    cv = CV(n, MUD)
    sp = E.spawns8(n)
    cy = (n - 1) / 2.0
    cv.band_v(74, 125, HIGHGRASS)
    for r in range(n):
        cen = cy + n1(r, 1.3, 0.031, 2.2)
        half = 15.0 + n1(r, 4.7, 0.024, 2.0)
        for dc in range(int(-half), int(half) + 1):
            c = int(round(cen)) + dc
            if 0 <= c < n:
                cv.g[r][c] = WATER
        for dc in (-half - 2, -half - 1, half + 1, half + 2):
            c = int(round(cen)) + int(dc)
            if 0 <= c < n:
                cv.g[r][c] = SHOAL
    for (iy, irad, iwid) in ((46, 8, 12), (100, 10, 14), (154, 8, 12)):
        ic = cy + n1(iy, 1.3, 0.031, 2.2)
        for r in range(n):
            for c in range(n):
                if ((r - iy) / irad) ** 2 + ((c - ic) / iwid) ** 2 <= 1.0:
                    cv.g[r][c] = GRASS
    for y0 in (26, 72, 116, 162):
        for r in range(y0 - 4, y0 + 5):
            if 0 <= r < n:
                for c in range(n):
                    if cv.g[r][c] in WAT:
                        cv.g[r][c] = SHOAL
    E.protect(cv, sp, 13)
    cv.mark(gap=1)
    rng = random.Random(202)
    for (ry, rx, rad, cat, sq) in [
        (20, 32, 9, GRASS, 1.0), (180, 32, 9, GRASS, 1.0),
        (20, 168, 9, GRASS, 1.0), (180, 168, 9, GRASS, 1.0),
        (100, 22, 10, GRASS, 1.2), (100, 178, 10, GRASS, 1.2),
        (60, 28, 7, STONE, 1.0), (140, 28, 7, STONE, 1.0),
        (60, 172, 7, STONE, 1.0), (140, 172, 7, STONE, 1.0),
        (36, 44, 6, WATER, 1.0), (164, 44, 6, WATER, 1.0),
        (36, 156, 6, WATER, 1.0), (164, 156, 6, WATER, 1.0),
        (86, 20, 5, SAND, 1.0), (114, 20, 5, SAND, 1.0),
        (86, 180, 5, SAND, 1.0), (114, 180, 5, SAND, 1.0),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.26, squash=sq)
    finish(cv, sp)
    return cv, sp, [(int(cy), int(cy))]


# ================================================================ 图三 双潭虹桥
def build_twinate(n=200):
    cv = CV(n, SAND)
    sp = E.spawns8(n)
    cy = (n - 1) / 2.0
    cv.band_h(86, 113, GRASS)
    for (ly, rx, ry) in ((52, 44, 27), (147, 44, 27)):
        for r in range(n):
            for c in range(n):
                if ((c - cy) / rx) ** 2 + ((r - ly) / ry) ** 2 <= 1.0:
                    cv.g[r][c] = WATER
        for r in range(n):
            for c in range(n):
                if ((c - cy) / (rx + 3)) ** 2 + ((r - ly) / (ry + 3)) ** 2 <= 1.0 and cv.g[r][c] not in WAT:
                    cv.g[r][c] = SHOAL
    for ly in (52, 147):
        cv.disc(ly, cy, 7.0, SAND)
    for tx in (44, 100, 156):
        cv.rect(int(cy) - 6, int(cy) + 6, tx - 6, tx + 6, STONE)
    cv.mark(gap=2)
    E.protect(cv, sp, 13)
    rng = random.Random(303)
    for (ry, rx, rad, cat) in [
        (14, 30, 11, STONE), (186, 30, 11, STONE),
        (14, 170, 11, STONE), (186, 170, 11, STONE),
        (52, 18, 7, STONE), (147, 18, 7, STONE),
        (52, 182, 7, STONE), (147, 182, 7, STONE),
        (28, 62, 8, MUD), (172, 62, 8, MUD),
        (28, 138, 8, MUD), (172, 138, 8, MUD),
        (74, 26, 7, DIRT), (126, 26, 7, DIRT),
        (74, 174, 7, DIRT), (126, 174, 7, DIRT),
        (100, 14, 6, MUD), (100, 186, 6, MUD),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.30)
    finish(cv, sp)
    return cv, sp, [(100, 100), (100, 44), (100, 156)]


# ================================================================ 图四 长河三渡
def build_frozenriver(n=200):
    cv = CV(n, SNOW)
    sp = E.spawns8(n)
    cy = (n - 1) / 2.0
    rng = random.Random(404)
    for r in range(n):
        cen = cy + n1(r, 2.1, 0.026, 5.0)
        for dc in range(-20, 21):
            c = int(round(cen)) + dc
            if 0 <= c < n:
                cv.g[r][c] = STONE
    for r in range(n):
        cen = cy + n1(r, 2.1, 0.026, 5.0)
        half = 11.0 + n1(r, 5.3, 0.019, 2.0)
        for dc in range(int(-half), int(half) + 1):
            c = int(round(cen)) + dc
            if 0 <= c < n:
                cv.g[r][c] = WATER
        for dc in (-half - 1, half + 1):
            c = int(round(cen)) + int(dc)
            if 0 <= c < n:
                cv.g[r][c] = SHOAL
    for y0 in (34, 100, 166):
        for r in range(y0 - 5, y0 + 6):
            if 0 <= r < n:
                for c in range(n):
                    if cv.g[r][c] in WAT:
                        cv.g[r][c] = SHOAL
    E.protect(cv, sp, 14)
    for (ry, rx, rad) in [(14, 66, 13), (186, 66, 13), (14, 134, 13), (186, 134, 13)]:
        cv.disc(ry, rx, rad + 6, STONE, blk_ok=False)
        cv.disc(ry, rx, rad, HIGHSTONE, blk_ok=False)
    for (ry, rx, rad) in [(52, 30, 8), (148, 30, 8), (52, 170, 8), (148, 170, 8)]:
        cv.disc(ry, rx, rad + 5, STONE, blk_ok=False)
        cv.disc(ry, rx, rad, WATER, blk_ok=False)
    cv.mark(gap=1)
    for (ry, rx, rad) in [(34, 64, 6), (166, 64, 6), (34, 136, 6), (166, 136, 6),
                          (76, 100, 5), (124, 100, 5)]:
        patch(cv, ry, rx, rad, MUD, rng, lobes=7, jit=0.3)
    finish(cv, sp, 7)
    return cv, sp, [(34, 100), (166, 100), (76, 40), (124, 160)]


# ================================================================ 图五 铁脊关山
def build_ironridge(n=200):
    cv = CV(n, DIRT)
    sp = E.spawns8(n)
    cy = (n - 1) / 2.0
    rng = random.Random(505)
    GATES = [44, 100, 156]
    wall_h(cv, lambda c: cy + n1(c, 3.3, 0.028, 5.0), hs=14, hh=8,
           gates=GATES, gate_half=11, gm=12)
    for gc in GATES:                    # 关隘：整段高石降为石（可通行，且类别与相邻列一致→永不三岔）
        for c in range(gc - 11, gc + 12):
            if not (0 <= c < n):
                continue
            rg = int(round(cy + n1(c, 3.3, 0.028, 5.0)))
            for dr in range(-9, 10):
                r = rg + dr
                if 0 <= r < n and cv.g[r][c] == HIGHSTONE:
                    cv.g[r][c] = STONE
    E.protect(cv, sp, 15)
    cv.mark(gap=1)
    for (ry, rx, rad, cat) in [
        (22, 34, 10, GRASS), (22, 166, 10, GRASS),
        (178, 34, 10, GRASS), (178, 166, 10, GRASS),
        (60, 46, 9, GRASS), (60, 154, 9, GRASS),
        (140, 46, 9, GRASS), (140, 154, 9, GRASS),
        (16, 100, 9, GRASS), (184, 100, 9, GRASS),
        (36, 16, 8, STONE), (164, 16, 8, STONE),
        (36, 184, 8, STONE), (164, 184, 8, STONE),
        # —— 补地形层次：南北草谷、泥沼洼地、山间湖、沙洲 ——
        (52, 76, 11, GRASS), (148, 76, 11, GRASS),
        (52, 124, 11, GRASS), (148, 124, 11, GRASS),
        (72, 64, 8, MUD), (128, 64, 8, MUD),
        (72, 136, 8, MUD), (128, 136, 8, MUD),
        (72, 100, 7, WATER), (128, 100, 7, WATER),
        (70, 30, 7, SAND), (130, 30, 7, SAND),
        (70, 170, 7, SAND), (130, 170, 7, SAND),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.28)
    for (ry, rx, rad) in [(24, 34, 6), (24, 166, 6), (176, 34, 6), (176, 166, 6),
                          (60, 46, 5), (60, 154, 5), (140, 46, 5), (140, 154, 5),
                          (52, 76, 7), (148, 124, 7), (52, 124, 6), (148, 76, 6)]:
        patch(cv, ry, rx, rad, HIGHGRASS, rng, lobes=7, jit=0.3, only={GRASS})
    finish(cv, sp, 5)
    return cv, sp, [(44, 100), (156, 100), (100, 100), (72, 34), (128, 166)]


# ================================================================ 图六 芜原碎境
def build_highland(n=200):
    """破碎荒原：两道蜿蜒高石山脉把荒原切成 3 个战区。

    抬升陆军的三个要点：
      1) 高石悬崖不可通行 —— 机甲与空军无法再在整图随意机动；
      2) 每道山 3 处「宽隘口」（全宽通行）+ 5 处「窄缝」（仅 3 格，大型机甲挤
         不过去、坦克可以）——陆军因此拥有机甲没有的包抄路线；
      3) 沼泽水塘 + 被切碎的战区，把交战距离压进近战范围。
    山脉剖面恒为 高草 → 草坡 → 裸岩 → 高石（各层两两都有过渡块）。
    """
    cv = CV(n, HIGHGRASS)
    sp = E.spawns8(n)
    NODES = [(30, 34), (30, 100), (30, 166),
             (74, 26), (74, 74), (74, 126), (74, 174),
             (126, 26), (126, 74), (126, 126), (126, 174),
             (170, 34), (170, 100), (170, 166)]
    for (nr, nc) in NODES:
        rad = 13 if (nr in (30, 170) and nc == 100) else 10
        cv.disc(nr, nc, rad, GRASS)
        cv.ring(nr, nc, rad * 0.62, rad * 0.82, STONE)
    cv.disc((n - 1) / 2.0, (n - 1) / 2.0, 18, GRASS)
    cv.ring((n - 1) / 2.0, (n - 1) / 2.0, 18, 20, STONE)
    cv.ring((n - 1) / 2.0, (n - 1) / 2.0, 9.5, 11.5, STONE)

    # ── 蜿蜒高石山脉（只画左半 x≈67，右半由 snap_mirror 镜像 → 严格对称）
    GATES = [40, 100, 160]                                    # 宽隘口
    SLITS = [(24, 4), (72, 4), (120, 4), (176, 4)]   # 窄缝：仅 3 格宽（避开隘口区间）
    for r in range(n):
        wc = int(round(67 + n1(r, 2.2, 0.021, 4.0)))
        is_gate = any(abs(r - gy) <= 7 for gy in GATES)
        is_slit = any(abs(r - sr) <= sh for sr, sh in SLITS)
        for dc in range(-11, 12):                              # 草坡
            c = wc + dc
            if 0 <= c < n:
                cv.g[r][c] = GRASS
        for dc in list(range(-8, -5)) + list(range(6, 9)):      # 裸岩
            c = wc + dc
            if 0 <= c < n:
                cv.g[r][c] = STONE
        if is_gate:
            continue                                           # 隘口：取消高石 → 全宽通行
        if is_slit:
            for dc in range(-1, 2):                            # 窄缝：只留 3 格草
                c = wc + dc
                if 0 <= c < n:
                    cv.g[r][c] = GRASS
            for dc in list(range(-5, -2)) + list(range(2, 6)):
                c = wc + dc
                if 0 <= c < n:
                    cv.g[r][c] = HIGHSTONE
        else:
            for dc in range(-5, 6):                            # 高石悬崖
                c = wc + dc
                if 0 <= c < n:
                    cv.g[r][c] = HIGHSTONE

    # ── 沼泽水塘（先铺再隔离，避免走廊贴上来形成三岔）
    BOGS = [(52, 10, 8), (100, 10, 8), (148, 10, 8),
            (60, 99, 10), (140, 99, 10)]
    for (ry, rx, rad) in BOGS:
        cv.disc(ry, rx, rad, MUD)
        cv.disc(ry, rx, rad - 4, WATER)
    for (ry, rx, rad) in BOGS:
        for dr in range(-rad - 1, rad + 2):
            for dc in range(-rad - 1, rad + 2):
                r, c = ry + dr, rx + dc
                if 0 <= r < n and 0 <= c < n:
                    cv.blk[r][c] = 1

    # ── 据点走廊（被山脉切断 → 必须走隘口或窄缝；且不贴沼泽）
    def path(a, b, half=4):
        (r0, c0), (r1, c1) = a, b
        steps = int(max(abs(r1 - r0), abs(c1 - c0)) * 1.7) + 1
        for i in range(steps + 1):
            t = i / steps
            rr, cc = r0 + (r1 - r0) * t, c0 + (c1 - c0) * t
            for dr in range(-half, half + 1):
                for dc in range(-half, half + 1):
                    r, c = int(round(rr)) + dr, int(round(cc)) + dc
                    if 0 <= r < n and 0 <= c < n and cv.g[r][c] == HIGHGRASS and not cv.blk[r][c]:
                        cv.g[r][c] = GRASS
    for i in range(len(NODES)):
        for j in range(i + 1, len(NODES)):
            if math.dist(NODES[i], NODES[j]) < 52:
                path(NODES[i], NODES[j])

    finish(cv, sp, 7)
    return cv, sp, [(int((n - 1) / 2), int((n - 1) / 2)), (30, 34), (170, 34)]


# ================================================================ 图七 裂谷三径
def build_rift(n=220):
    """灰岩高原 + 中央大峡谷（谷底草 → 石坡 → 高石山），四谷口。底色=石。"""
    cv = CV(n, STONE)
    sp = E.spawns10(n)
    cy = (n - 1) / 2.0
    GATES = [int(n * 0.2), int(n * 0.4), int(n * 0.6), int(n * 0.8)]
    GH = 13
    for r in range(n):
        cen = cy + n1(r, 2.7, 0.023, 5.0)
        cc0 = int(round(cen))
        for dc in range(-15, 16):                 # 谷底草地
            c = cc0 + dc
            if 0 <= c < n:
                cv.g[r][c] = GRASS
        for dc in list(range(-23, -15)) + list(range(16, 24)):   # 石坡（可通行）
            c = cc0 + dc
            if 0 <= c < n:
                cv.g[r][c] = STONE
        for dc in list(range(-29, -23)) + list(range(24, 30)):   # 高石山壁（不可通行）
            c = cc0 + dc
            if 0 <= c < n:
                cv.g[r][c] = HIGHSTONE
    for gc in GATES:                    # 谷口：只把最外层高石降为石 → 石坡连成缓坡通道
        for r in range(gc - GH, gc + GH + 1):
            if not (0 <= r < n):
                continue
            cen = cy + n1(r, 2.7, 0.023, 5.0)
            for dc in list(range(-32, -23)) + list(range(24, 33)):
                c = int(round(cen)) + dc
                if 0 <= c < n and cv.g[r][c] == HIGHSTONE:
                    cv.g[r][c] = STONE
    E.protect(cv, sp, 13)
    cv.mark(gap=1)
    rng = random.Random(707)
    for (ry, rx, rad, cat) in [
        (16, 44, 11, GRASS), (n - 17, 44, 11, GRASS),
        (16, n - 45, 11, GRASS), (n - 17, n - 45, 11, GRASS),
        (n // 2, 14, 11, GRASS), (n // 2, n - 15, 11, GRASS),
        (56, 32, 8, SAND), (n - 57, 32, 8, SAND),
        (56, n - 33, 8, SAND), (n - 57, n - 33, 8, SAND),
        (26, n // 2, 7, SAND), (n - 27, n // 2, 7, SAND),
        (74, 26, 6, DIRT), (n - 75, 26, 6, DIRT),
        (74, n - 27, 6, DIRT), (n - 75, n - 27, 6, DIRT),
        # —— 补地貌：高原绿洲、土塬、盐沼 ——
        (int(n * 0.16), 60, 8, MUD), (n - 1 - int(n * 0.16), 60, 8, MUD),
        (int(n * 0.16), n - 61, 8, MUD), (n - 1 - int(n * 0.16), n - 61, 8, MUD),
        (int(n * 0.30), 40, 7, WATER), (n - 1 - int(n * 0.30), 40, 7, WATER),
        (int(n * 0.30), n - 41, 7, WATER), (n - 1 - int(n * 0.30), n - 41, 7, WATER),
        (int(n * 0.70), 44, 7, DIRT), (n - 1 - int(n * 0.70), 44, 7, DIRT),
        (int(n * 0.70), n - 45, 7, DIRT), (n - 1 - int(n * 0.70), n - 45, 7, DIRT),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.30)
    finish(cv, sp, 7)
    return cv, sp, [(GATES[0], n // 2), (GATES[2], n // 2), (GATES[1], n // 2)]


# ================================================================ 图八 残垣四门
def build_bastion(n=220):
    cv = CV(n, GRASS)
    sp = E.spawns10(n)
    cy = cx = (n - 1) / 2.0
    rng = random.Random(808)
    for (rad, hs, hh, gates) in [
        (24, 5.0, 2.0, [(0, 10), (90, 10), (180, 10), (270, 10)]),
        (44, 5.5, 2.2, [(45, 9), (135, 9), (225, 9), (315, 9)]),
        (64, 6.0, 2.5, [(20, 9), (110, 9), (200, 9), (290, 9)]),
    ]:
        ring_wall(cv, cy, cx, rad, hs, hh, gates, gm_deg=10)
    cv.disc(cy, cy, 14, GRASS)
    cv.ring(cy, cy, 14, 16.5, STONE, gates=[(a, 12) for a in (0, 90, 180, 270)])
    cv.ring(cy, cy, 6.0, 8.0, STONE, gates=[(a, 22) for a in (45, 135, 225, 315)])
    E.protect(cv, sp, 14)
    cv.mark(gap=1)
    for (rad, angs, cat, rr) in [(34, (0, 90, 180, 270), HIGHGRASS, 2.6),
                                 (54, (45, 135, 225, 315), MUD, 2.4)]:
        for a in angs:
            ar = math.radians(a)
            patch(cv, cy + rad * math.sin(ar), cy + rad * math.cos(ar), rr, cat, rng,
                  lobes=7, jit=0.28)
    for (ry, rx, rad, cat) in [
        (16, 34, 10, HIGHSTONE), (n - 17, 34, 10, HIGHSTONE),
        (16, n - 35, 10, HIGHSTONE), (n - 17, n - 35, 10, HIGHSTONE),
        (n // 2, 15, 10, HIGHGRASS), (n // 2, n - 16, 10, HIGHGRASS),
        (30, 68, 8, HIGHGRASS), (n - 31, 68, 8, HIGHGRASS),
        (30, n - 69, 8, HIGHGRASS), (n - 31, n - 69, 8, HIGHGRASS),
        (60, 20, 7, MUD), (n - 61, 20, 7, MUD),
        (60, n - 21, 7, MUD), (n - 61, n - 21, 7, MUD),
        (n // 2 - 14, n // 2, 8, MUD), (n // 2 + 14, n // 2, 8, MUD),
    ]:
        patch(cv, ry, rx, rad, cat, rng, lobes=8, jit=0.30)
    finish(cv, sp, 8)
    c0 = int((n - 1) / 2)
    return cv, sp, [(c0, c0), (c0 - 34, c0 - 34), (c0 + 34, c0 + 34), (c0 - 10, c0 + 30), (c0 + 10, c0 - 30)]


# ================================================================ 产出
JOBS = [
    ("图一", build_ring, 200, "环渊圣坛", "同心环 · 草原+石台"),
    ("图二", build_longlake, 200, "长湖映月", "纵向长湖 · 沼泽+芦苇"),
    ("图三", build_twinate, 200, "双潭虹桥", "上下双湖 · 沙漠"),
    ("图四", build_frozenriver, 200, "长河三渡", "冰河三渡 · 雪原"),
    ("图五", build_ironridge, 200, "铁脊关山", "横贯山脊 · 黄土"),
    ("图六", build_highland, 200, "芜原碎境", "网状据点 · 高草荒原"),
    ("图七", build_rift, 220, "裂谷四径", "大峡谷四谷口 · 灰岩高原"),
    ("图八", build_bastion, 220, "残垣四门", "三重残垣 · 草原"),
]


def one(name, builder, n, tag, desc):
    cv, sp, mines = builder(n)
    # 修边：去孤立尖刺 / 悬空格 / 仅对角相连的伪影（skill 权威指标，门槛 99.5%）
    try:
        rate, iso, c0, dg, it = G5.edge_auto_fix(cv.g, threshold=99.5, max_iters=12)
    except RuntimeError:
        rate, iso, c0, dg = C.edge_pass_rate(cv.g)
    # 修边可能引入新的三类交汇 → 复查并修复；收尾只做花屏修复，避免再次引入冲突
    for _ in range(5):
        if E.nf(cv.g) == 0:
            break
        E.fix_gently(cv.g, it=6)
        if E.nf(cv.g) == 0:
            break
        G5.clean_all(cv.g, iters=1)
        E.fix_gently(cv.g, it=3)
    for _ in range(6):                       # 收尾：只修花屏，不动边缘结构
        if E.nf(cv.g) == 0:
            break
        E.fix_gently(cv.g, it=8)
    rate, iso, c0, dg = C.edge_pass_rate(cv.g)
    flower = E.nf(cv.g)
    bad, _ = E.bfs_pairs(cv.g, sp)
    items = E.place_mines(cv, sp, mines)
    _rng = random.Random(abs(hash(name)) & 0xffff)
    decor = E.make_decor(cv, _rng)
    trees = E.make_trees(cv, _rng, items, sp)
    ntree = sum(1 for r in range(n) for c in range(n) if trees[r][c])
    out = os.path.join(OUT, f"{name}_{tag}.tmx")
    issues = E.write_tmx(cv, decor, items, sp, out, trees=trees)
    nmine = sum(1 for r in range(n) for c in range(n) if items[r][c])
    cnt = cv.count()
    tot = n * n
    top = " ".join(f"{E.NM.get(k, k)}{v * 100 // tot}%" for k, v in cnt.most_common(5))
    kinds = sum(1 for k, v in cnt.items() if v > tot * 0.004)
    print(f"[{name}] {tag}: 花屏={flower} 修边{rate:.2f}% 尖刺{iso} 悬空{c0} 对角{dg} 矿={nmine} 树={ntree} 地形={kinds}种 | {top}")
    for it in issues[:3]:
        print("     !", it)
    return dict(name=name, tag=tag, desc=desc, out=out, flower=flower, bad=bad,
                mines=nmine, kinds=kinds, n=n, cnt=cnt)


def main():
    os.makedirs(OUT, exist_ok=True)
    res = [one(*j) for j in JOBS]
    print("\n=== 汇总 ===")
    for r in res:
        ok = "OK " if (r["flower"] == 0 and r["bad"] == 0) else "!! "
        print(f"  {ok}{r['name']} {r['tag']:<6} {r['n']}px 花屏{r['flower']:>2} 断路{r['bad']:>2} 矿{r['mines']:>3} 地形{r['kinds']:>2}种  {r['desc']}")


if __name__ == "__main__":
    main()
