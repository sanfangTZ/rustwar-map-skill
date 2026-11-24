#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 『林海雪岭』 5V5 竞技图 (Snowy Ridge Divide) 生成器

设计（完全重做，零水上搭桥）：
- 纯遭遇战：Triggers 仅 map_info + camera_start，零触发器。
- 左右对抗 5V5：左=偶 0/2/4/6/8（西部林海），右=奇 1/3/5/7/9（东部草原台地）。
- 中央一条『雪岭山脊』（HIGHSTONE 核心 + STONE 软边），把左右分开；山脊上开 3 个
  草地隘口（北/中/南），构成 3 条『纯陆地』地面通道——不挖水道、不架桥。
- 西侧林海：草地基底 + 连片针叶林(高草) + 土斑块 + 数座石丘 + 2 处湖泊(装饰水)。
- 东侧草原台地：草地基底 + 稀树灌丛(高草) + 沙地 + 岩石台地 + 干裂泥床。
- 中央隘口两侧撒石/高草作掩体，水晶落于隘口两端草地（需地面占领）。
- 空军不能定胜负：山脊天然割裂视野/机动，中央林地掩体密布，水晶深嵌地形。
"""
import os, random
import numpy as np
import gen_5v5_common as G

SIZE = G.SIZE
HIGHSTONE = G.HIGHSTONE
STONE, GRASS, DIRT, SAND, MUD, HIGHGRASS, WATER = G.STONE, G.GRASS, G.DIRT, G.SAND, G.MUD, G.HIGHGRASS, G.WATER
IMPASS = G.IMPASS

# 3 个山脊隘口（行带），山脊在此处断开成草地通道
PASS_BANDS = [(24, 46), (88, 112), (154, 176)]
SPINE_BASE = 100
# 验证用：每条通道矩形（跨山脊宽度）
BANDS_RECT = [(r0, r1, 84, 116) for (r0, r1) in PASS_BANDS]


def spine_fn(r):
    return SPINE_BASE + 8.0 * math.sin(r * 0.04) + 4.0 * G._vn(r * 0.3, 7.7, 1 / 45.0)


import math


def build_terrain(seed):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # ---------- 1) 中央雪岭山脊（隘口处断开） ----------
    skip = set()
    for (r0, r1) in PASS_BANDS:
        for r in range(r0 - 2, r1 + 3):
            skip.add(r)
    G.ridge(grid, spine_fn, base_half=9.0, core=3.0, rng=rng, skip=skip)
    # 隘口内强制纯草（清除脊线残留），并在两端留开阔口
    for (r0, r1) in PASS_BANDS:
        for r in range(r0, r1 + 1):
            for c in range(82, 118):
                if 0 <= c < W and grid[r][c] != WATER:
                    grid[r][c] = GRASS

    # ---------- 2) 西侧林海（偶队） ----------
    # 连片针叶林（高草）3~4 片
    for (hr, hc, rad) in [(58, 64, 11), (140, 58, 11), (100, 70, 9), (28, 50, 7)]:
        G.blob(grid, hr, hc, rad, HIGHGRASS, rng, lobes=5, jit=0.20, only=(GRASS, DIRT))
    # 石丘地标（远离出生走廊）
    for (sr, sc, rad) in [(150, 56, 6), (40, 46, 6), (110, 40, 5)]:
        G.blob(grid, sr, sc, rad, STONE, rng, lobes=6, jit=0.18, only=(GRASS, DIRT, HIGHGRASS, MUD))
    # 湖泊（装饰水，避开出生列与隘口）
    for (lr, lc, rad) in [(34, 34, 6), (166, 40, 6)]:
        G.blob(grid, lr, lc, rad - 1, WATER, rng, lobes=7, jit=0.12,
               only=(GRASS, DIRT, HIGHGRASS, MUD))
        G.blob(grid, lr, lc, rad + 2, G.SHOAL, rng, lobes=7, jit=0.12,
               only=(GRASS, DIRT, HIGHGRASS, MUD))
    # 泥洼（1 处）
    G.blob(grid, 118, 50, 5, MUD, rng, lobes=5, jit=0.20, only=(GRASS, DIRT, HIGHGRASS))

    # ---------- 3) 东侧草原台地（奇队） ----------
    # 稀树灌丛（高草）斑块
    for (hr, hc, rad) in [(60, 142, 10), (138, 138, 10), (100, 150, 8), (30, 156, 7)]:
        G.blob(grid, hr, hc, rad, HIGHGRASS, rng, lobes=5, jit=0.20, only=(GRASS, DIRT, SAND))
    # 岩石台地地标
    for (sr, sc, rad) in [(50, 164, 6), (150, 158, 6), (100, 178, 5)]:
        G.blob(grid, sr, sc, rad, STONE, rng, lobes=6, jit=0.18, only=(GRASS, DIRT, SAND))
    # 干裂泥床（2 处）
    for (mr, mc, rad) in [(118, 168, 5), (80, 150, 5)]:
        G.blob(grid, mr, mc, rad, MUD, rng, lobes=4, jit=0.22, only=(GRASS, DIRT, SAND))
    # 沙地基底斑块
    for (dr, dc, rad) in [(170, 160, 7), (40, 170, 7)]:
        G.blob(grid, dr, dc, rad, SAND, rng, lobes=6, jit=0.18, only=(GRASS, DIRT))

    # ---------- 4) 陆地细分层（打碎纯草连片） ----------
    G.detail_land(grid, rng)

    # ---------- 5) 山脊隘口：只强制脊线缺口为草，其余保持自然地貌并加有机纹理 ----------
    for (r0, r1) in PASS_BANDS:
        for r in range(r0, r1 + 1):
            sp = spine_fn(r)
            for c in range(max(0, int(sp) - 9), min(W, int(sp) + 10)):
                if grid[r][c] != WATER:
                    grid[r][c] = GRASS          # 脊线缺口（清晰的山口）
        # 隘口区域有机纹理（ dirt/高草/石 散布，避免完美绿矩形；三者均可通行，不破坏连通）
        for r in range(r0, r1 + 1):
            for c in range(80, 120):
                if grid[r][c] != GRASS:
                    continue
                v = G._vn(r, c, 1 / 7.0)
                if v > 0.50:
                    grid[r][c] = DIRT
                elif v < -0.60:
                    grid[r][c] = HIGHGRASS
                elif G._vn(r + 77, c, 1 / 5.0) > 0.70:
                    grid[r][c] = STONE
        # 隘口两端撒掩体（不在通道正中线，避免堵死）
        for rm in range(r0, r1 + 1):
            if rng.random() < 0.5:
                if grid[rm][86] in (GRASS, DIRT):
                    grid[rm][86] = HIGHGRASS if rng.random() < 0.6 else STONE
                if grid[rm][114] in (GRASS, DIRT):
                    grid[rm][114] = HIGHGRASS if rng.random() < 0.6 else STONE

    # ---------- 4.5) 中央对称掩体（林+石），打破中央开阔、抑空军、平衡左右 ----------
    # 严格关于 col=100 镜像，且全部落在隘口通道(列82~118)之外，不堵死通道。
    for (cr, cc, rad, cat) in [
        (70, 74, 8, HIGHGRASS), (130, 74, 8, HIGHGRASS),
        (70, 126, 8, HIGHGRASS), (130, 126, 8, HIGHGRASS),
        (100, 70, 7, STONE), (100, 130, 7, STONE),
        (60, 100, 7, STONE), (140, 100, 7, STONE),
    ]:
        G.blob(grid, cr, cc, rad, cat, rng, lobes=5, jit=0.22, only=(GRASS, DIRT))

    # ---------- 6) 中央区（隘口之间脊线两侧）起伏掩体 ----------
    for r in range(50, 150):
        for c in range(60, 140):
            if grid[r][c] != GRASS:
                continue
            v = G._noise(r + 500, c + 500)
            if v > 0.26:
                grid[r][c] = STONE
            elif v < -0.26:
                grid[r][c] = HIGHGRASS
            elif G._noise(r + 800, c + 800) > 0.5:
                grid[r][c] = MUD

    G.clean_highstone(grid)
    G.clean_all(grid)            # 通用修边：清除孤立尖刺/对角伪影（详见 edge_cleanup.md §A）
    return grid, rng


def get_crystals():
    cs = []
    for (r0, r1) in PASS_BANDS:
        rm = (r0 + r1) // 2
        cs.append((rm, 88))
        cs.append((rm, 112))
    return cs


def generate(seed=7, out="rw_5v5_ridge.tmx"):
    grid, rng = build_terrain(seed)
    rate, iso, cnt0, diagonly, iters = G.edge_auto_fix(grid)   # V4.1: 修边<98% 拒绝出图
    edge = (iso, cnt0, diagonly)            # 纯地形修边指标（铺点前，不含出生点草坪）
    spawns = G.get_spawns()
    G.protect_bases(grid, spawns)
    items = [[0] * SIZE for _ in range(SIZE)]
    G.place_res(items, grid, spawns)
    decor = G.make_decor(grid, rng, opts={"density": 1.0})
    crystals = get_crystals()
    tree, issues = G.write_tmx(grid, decor, items, spawns, crystals, out,
                               intro="【林海雪岭 5V5】\n中央雪岭山脊开三隘口，纯陆地对抗；拆光对手主基地获胜。")
    v = G.verify_connectivity(grid, spawns, BANDS_RECT)
    v["edge"] = edge
    return tree, spawns, grid, items, decor, crystals, issues, v


if __name__ == "__main__":
    out = "rw_5v5_ridge.tmx"
    chosen = None
    best = None
    for seed in (7, 13, 21, 42, 99, 123, 256, 333, 777, 2024):
        grid, rng = build_terrain(seed)
        spawns = G.get_spawns()
        G.protect_bases(grid, spawns)
        v = G.verify_connectivity(grid, spawns, BANDS_RECT)
        terr = G.Counter()
        for row in grid:
            for x in row:
                terr[x] += 1
        total = SIZE * SIZE
        gcc = G.largest_grass_cc(grid)
        ctr = G.central_max_terrain(grid)
        ok = (v["reachable"] and v["pair_ok"] and v["passages"] >= 3 and v["bal_diff"] < 15
              and len(terr) >= 9 and max(terr.values()) / total * 100 <= 55
              and 100 * gcc / total < 10 and ctr < 45)
        print(f"seed={seed} reach={v['reachable']} pair={v['pair_ok']} pass={v['passages']} "
              f"bal={v['bal_diff']:.1f}% types={len(terr)} max={max(terr.values())/total*100:.1f}% "
              f"gcc={100*gcc/total:.1f}% ctr={ctr:.1f}% ok={ok}")
        if ok and chosen is None:
            chosen = seed
            break
    if chosen is None:
        chosen = 7
        print("⚠ 未找到全达标种子，使用 seed=7。")
    tree, spawns, grid, items, decor, crystals, issues, v = generate(chosen, out)
    G.report(grid, items, decor, crystals, spawns, v, issues, "林海雪岭")
