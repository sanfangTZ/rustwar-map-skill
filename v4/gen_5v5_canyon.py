#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 『赤岩裂谷』 5V5 竞技图 (Red Rock Canyon) 生成器

设计（完全重做，零水上搭桥）：
- 纯遭遇战：Triggers 仅 map_info + camera_start，零触发器。
- 左右对抗 5V5：左=偶 0/2/4/6/8（西部绿洲高原），右=奇 1/3/5/7/9（东部赤岩台地）。
- 中央一条『干峡谷』：南北向 HIGHSTONE 崖壁夹一条可行走的土质地面走廊（纯陆地，无半滴水、无桥）。
  峡谷只占据地图中段（行 60~140）；其上方(0~60)与下方(140~200)是开阔『草鞍部』。
  → 左右靠 3 条纯陆地路线连通：北鞍部 / 峡谷地面走廊 / 南鞍部。
- 西侧绿洲高原：草地 + 连片林地(高草) + 土斑块 + 湖泊(装饰水) + 石丘。
- 东侧赤岩台地：草地 + 沙地 + 岩石台地 + 稀树灌丛(高草) + 干裂泥床。
- 中央峡谷地面走廊 + 两鞍部撒石/高草掩体；水晶落于走廊与鞍部草地。
- 空军不能定胜负：峡谷崖壁割裂机动，中央林地/石丘密布掩体，水晶嵌地形需地面占领。
"""
import os, math, random
import numpy as np
import gen_5v5_common as G

SIZE = G.SIZE
HIGHSTONE = G.HIGHSTONE
STONE, GRASS, DIRT, SAND, MUD, HIGHGRASS, WATER = G.STONE, G.GRASS, G.DIRT, G.SAND, G.MUD, G.HIGHGRASS, G.WATER
IMPASS = G.IMPASS

GORGE_R0, GORGE_R1 = 60, 140     # 峡谷占据的行范围
WALL_HW = 10                      # 崖壁半宽（距脊线）——加宽让峡谷真正"读得出来"
FLOOR_HW = 4                      # 可行走地面走廊半宽（距脊线）
SPINE_BASE = 100

# 验证用：3 条通道矩形
BANDS_RECT = [
    (0, GORGE_R0, 84, 116),                       # 北鞍部
    (GORGE_R0, GORGE_R1, SPINE_BASE - FLOOR_HW - 1, SPINE_BASE + FLOOR_HW + 1),  # 峡谷地面走廊
    (GORGE_R1, SIZE, 84, 116),                    # 南鞍部
]


def spine_fn(r):
    return SPINE_BASE + 5.0 * math.sin(r * 0.05) + 3.0 * G._vn(r * 0.3, 9.3, 1 / 50.0)


def build_terrain(seed):
    rng = random.Random(seed)
    H = W = SIZE
    grid = [[GRASS] * W for _ in range(H)]

    # ---------- 1) 中央干峡谷（中段 HIGHSTONE 崖壁 + 可行走土质地走廊） ----------
    # 脊线固定在 col=100，保证左右严格镜像对称（平衡≈0）；
    # 崖壁宽度低频"呼吸"+逐格噪声 → 有机峡谷轮廓；外圈 STONE 缓坡过渡。
    SP = 100.0
    for r in range(GORGE_R0, GORGE_R1 + 1):
        breath = 2.2 * math.sin(r * 0.07) + 1.2 * math.sin(r * 0.023 + 1.7)
        for c in range(W):
            d = abs(c - SP)
            wn = 1.4 * G._vn(r, c, 1 / 9.0) + 0.8 * G._vn(r, c, 1 / 4.0)
            fh = FLOOR_HW + 0.7 * G._vn(r, c, 1 / 6.0) + 0.8 * math.sin(r * 0.09 + 0.6)
            wh = WALL_HW + breath + wn
            if d <= fh:
                grid[r][c] = DIRT          # 峡谷地面走廊（可行走）
            elif d <= wh:
                grid[r][c] = HIGHSTONE     # 崖壁（不可通行）
            elif d <= wh + 2.2:
                grid[r][c] = STONE         # 崖壁外缓坡（软过渡）
    # 崖壁上下端稍作收口，避免与鞍部硬切
    for r in (GORGE_R0 - 2, GORGE_R0 - 1, GORGE_R1 + 1, GORGE_R1 + 2):
        if 0 <= r < H:
            for c in range(W):
                d = abs(c - SP)
                wn = 1.4 * G._vn(r, c, 1 / 9.0)
                fh = FLOOR_HW + 0.6 * G._vn(r, c, 1 / 6.0)
                wh = WALL_HW + wn
                if d <= fh:
                    grid[r][c] = DIRT
                elif d <= wh:
                    grid[r][c] = HIGHSTONE

    # ---------- 2) 西侧绿洲高原（偶队） ----------
    for (hr, hc, rad) in [(58, 60, 12), (140, 56, 11), (100, 66, 9), (30, 48, 8)]:
        G.blob(grid, hr, hc, rad, HIGHGRASS, rng, lobes=5, jit=0.20, only=(GRASS, DIRT))
    for (sr, sc, rad) in [(150, 54, 6), (44, 44, 6), (105, 38, 5)]:
        G.blob(grid, sr, sc, rad, STONE, rng, lobes=6, jit=0.18, only=(GRASS, DIRT, HIGHGRASS, MUD))
    for (lr, lc, rad) in [(34, 32, 6), (34, 168, 6)]:
        G.blob(grid, lr, lc, rad - 1, WATER, rng, lobes=7, jit=0.12, only=(GRASS, DIRT, HIGHGRASS, MUD))
        G.blob(grid, lr, lc, rad + 2, G.SHOAL, rng, lobes=7, jit=0.12, only=(GRASS, DIRT, HIGHGRASS, MUD))
    G.blob(grid, 120, 48, 5, MUD, rng, lobes=5, jit=0.20, only=(GRASS, DIRT, HIGHGRASS))

    # ---------- 3) 东侧赤岩台地（奇队） ----------
    for (hr, hc, rad) in [(60, 140, 11), (138, 136, 11), (100, 150, 9), (32, 156, 8)]:
        G.blob(grid, hr, hc, rad, HIGHGRASS, rng, lobes=5, jit=0.20, only=(GRASS, DIRT, SAND))
    for (sr, sc, rad) in [(50, 162, 6), (150, 156, 6), (100, 176, 5)]:
        G.blob(grid, sr, sc, rad, STONE, rng, lobes=6, jit=0.18, only=(GRASS, DIRT, SAND))
    for (mr, mc, rad) in [(118, 166, 5), (80, 150, 5)]:
        G.blob(grid, mr, mc, rad, MUD, rng, lobes=4, jit=0.22, only=(GRASS, DIRT, SAND))
    for (dr, dc, rad) in [(172, 158, 7), (165, 40, 7)]:
        G.blob(grid, dr, dc, rad, SAND, rng, lobes=6, jit=0.18, only=(GRASS, DIRT))

    # ---------- 4) 陆地细分层（打碎纯草连片） ----------
    G.detail_land(grid, rng)

    # ---------- 4.5) 中央对称掩体（林+石）——放在峡谷外侧翼，让峡谷本体凸显 ----------
    # 严格关于 col=100 镜像：左(col<100) 与 右(col>100) 成对布置。
    for (cr, cc, rad, cat) in [
        (80, 66, 6, HIGHGRASS), (120, 66, 6, HIGHGRASS),
        (80, 134, 6, HIGHGRASS), (120, 134, 6, HIGHGRASS),
        (70, 60, 7, STONE), (130, 60, 7, STONE),
        (70, 140, 7, STONE), (130, 140, 7, STONE),
    ]:
        G.blob(grid, cr, cc, rad, cat, rng, lobes=5, jit=0.22, only=(GRASS, DIRT, SAND))

    # ---------- 5) 中央峡谷地面走廊 + 两鞍部掩体（维护可行走） ----------
    # 峡谷走廊强制土/草（清除任何误植），两侧崖壁保持 HIGHSTONE
    SP = 100.0
    for r in range(GORGE_R0, GORGE_R1 + 1):
        for c in range(W):
            d = abs(c - SP)
            if d <= FLOOR_HW + 1 and grid[r][c] != HIGHSTONE:
                grid[r][c] = DIRT
            elif d <= WALL_HW + 1:
                grid[r][c] = HIGHSTONE
    # 鞍部撒石/高草掩体（不在正中线堵死）
    for r in range(6, GORGE_R0 - 4):
        if rng.random() < 0.45:
            if grid[r][88] in (GRASS, DIRT):
                grid[r][88] = HIGHGRASS if rng.random() < 0.6 else STONE
            if grid[r][112] in (GRASS, DIRT):
                grid[r][112] = HIGHGRASS if rng.random() < 0.6 else STONE
    for r in range(GORGE_R1 + 4, SIZE - 6):
        if rng.random() < 0.45:
            if grid[r][88] in (GRASS, DIRT):
                grid[r][88] = HIGHGRASS if rng.random() < 0.6 else STONE
            if grid[r][112] in (GRASS, DIRT):
                grid[r][112] = HIGHGRASS if rng.random() < 0.6 else STONE

    # ---------- 6) 中央区起伏掩体（概率散布，保持开阔衬出峡谷，避免糊成绿板） ----------
    for r in range(40, 160):
        for c in range(60, 140):
            if grid[r][c] not in (GRASS, DIRT):
                continue
            if rng.random() < 0.40:
                v = G._noise(r + 400, c + 400)
                if v > 0.10:
                    grid[r][c] = STONE
                elif v < -0.10:
                    grid[r][c] = HIGHGRASS
                elif G._noise(r + 700, c + 700) > 0.30:
                    grid[r][c] = MUD

    # ---------- 6.5) 两鞍部有机纹理（避免大块平坦草毯） ----------
    for r in list(range(4, GORGE_R0 - 2)) + list(range(GORGE_R1 + 2, SIZE - 4)):
        for c in range(78, 122):
            if grid[r][c] != GRASS:
                continue
            v = G._vn(r, c, 1 / 7.0)
            if v > 0.52:
                grid[r][c] = DIRT
            elif v < -0.60:
                grid[r][c] = HIGHGRASS
            elif G._vn(r + 55, c, 1 / 5.0) > 0.72:
                grid[r][c] = STONE

    G.clean_highstone(grid)
    G.clean_all(grid)            # 通用修边：清除孤立尖刺/对角伪影（详见 edge_cleanup.md §A）
    return grid, rng


def get_crystals():
    return [(82, SPINE_BASE), (118, SPINE_BASE),
            (30, SPINE_BASE), (170, SPINE_BASE)]


def generate(seed=7, out="rw_5v5_canyon.tmx"):
    grid, rng = build_terrain(seed)
    rate, iso, cnt0, diagonly, iters = G.edge_auto_fix(grid)   # V4.1: 修边<98% 拒绝出图
    edge = (iso, cnt0, diagonly)            # 纯地形修边指标（铺点前，不含出生点草坪）
    spawns = G.get_spawns()
    G.protect_bases(grid, spawns)
    items = [[0] * SIZE for _ in range(SIZE)]
    G.place_res(items, grid, spawns)
    decor = G.make_decor(grid, rng, opts={
        "density": 1.0,
        "forest_tiles": [G.FORM, G.ROOT, G.FORM, G.SPIRE2],   # 干旱灌丛/枯根，不用雪松
        "sand_tiles": [G.FORM, G.ROCKS, G.TUFT1],
    })
    crystals = get_crystals()
    tree, issues = G.write_tmx(grid, decor, items, spawns, crystals, out,
                               intro="【赤岩裂谷 5V5】\n中央干峡谷+南北草鞍部，纯陆地三通道对抗；拆光对手主基地获胜。")
    v = G.verify_connectivity(grid, spawns, BANDS_RECT)
    v["edge"] = edge
    return tree, spawns, grid, items, decor, crystals, issues, v


if __name__ == "__main__":
    out = "rw_5v5_canyon.tmx"
    chosen = None
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
    G.report(grid, items, decor, crystals, spawns, v, issues, "赤岩裂谷")