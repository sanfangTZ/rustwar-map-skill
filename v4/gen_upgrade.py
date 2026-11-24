#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""圆弧法权 V3 · 有机化升级（走 A4 已验证的完整约束管线，只调参数，不发明结构）
有机感来源：湖岸抖动 jit 0.07→0.22（自然海湾）、团块片数全部加密（山8→14/林9→16/泥8→12/石6→10/土4→8）
可靠保证：完全照抄 A4.build_terrain 的 forbid/桥窗/出生清场/镜像/水顶点清理顺序 → 零花屏
"""
import os, sys, math, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import gen_4v4_arena as A4
import gen_combined as C
import gen_koth as K
import gen_pure_all as P
from collections import Counter

W = H = 200
GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SHOAL, WATER = 23, 7
HIGHGRASS, HIGHSTONE = 12, 14
LAKE_C = (100.0, 99.5)
LAKE_R = 34
SPAWN_YS = [28, 76, 124, 172]
LEFT_X, RIGHT_X = 30, 169


def get_spawns():
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, [0, 2, 4, 6])] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, [1, 3, 5, 7])])


def build_arc_v3(seed=11):
    rng = random.Random(seed)
    grid = [[GRASS] * W for _ in range(H)]

    # 1) 有机大湖（jit 0.22：自然海湾/岬角，半径带宽度恒定 → 不花屏）
    A4.build_lake(grid, LAKE_C[0], LAKE_C[1], LAKE_R, rng, phase=rng.uniform(0, 6), jit=0.34)

    # 2) 中央法坛岛（略缩小，留出更多环湖水域）
    A4.carve_islands(grid, [(100.0, 99.5, 9, 4)])
    island_mask = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if math.hypot(r - 100.0, c - 99.5) <= 9 + 4:
                island_mask[r][c] = 1

    # 3) 海陆桥（同 A4）
    BRIDGES = [(95, 105, 46, 90), (95, 105, 109, 153)]
    bridge_mask = [[0] * W for _ in range(H)]
    for (r0, r1, c0, c1) in BRIDGES:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                bridge_mask[r][c] = 1

    A4._clean_water_vertices(grid)

    # 4) forbid：水族+沙 + 外扩 3 缓冲 + 岛 + 桥 + 出生±3 + 中立矿±2（照抄 A4）
    forbid = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] in (WATER, 8, 9, SHOAL, SAND) or bridge_mask[r][c]:
                forbid[r][c] = 1
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
    for (nr, nc) in P.mirror_nodes(P.NEUTRAL_8P):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = nr + dr, nc + dc
                if 0 <= r < H and 0 <= c < W:
                    forbid[r][c] = 1

    # 5) 山体（14 座，比 A4 的 8 座加密）
    mountain_specs = [
        (18, 18, 11), (18, 78, 10), (181, 18, 11), (181, 78, 10),
        (100, 14, 10), (100, 48, 9),
        (52, 12, 8), (148, 12, 8),
        (44, 26, 6), (156, 26, 6), (100, 178, 8), (70, 14, 6), (130, 14, 6), (100, 84, 5),
    ]
    for (mr, mc, mr_) in mountain_specs:
        A4.place_blob(grid, forbid, mr, mc, mr_, HIGHSTONE, rng, lobes=9, jit=0.26)

    # 6) 森林（16 片）
    forest_specs = [
        (28, 52, 10), (76, 52, 10), (124, 52, 10), (172, 52, 10),
        (100, 62, 9),
        (52, 82, 8), (148, 82, 8),
        (100, 30, 8), (100, 170, 8),
        (30, 70, 7), (170, 70, 7), (30, 130, 7), (170, 130, 7),
        (60, 44, 6), (140, 44, 6), (100, 120, 7),
    ]
    for (fr, fc, fr_) in forest_specs:
        A4.place_blob(grid, forbid, fr, fc, fr_, HIGHGRASS, rng, lobes=8, jit=0.28)

    # 7) 泥沼（12 片）
    mud_specs = [
        (52, 26, 10), (148, 26, 10),
        (100, 30, 9), (100, 170, 9),
        (60, 62, 7), (140, 62, 7), (60, 138, 7), (140, 138, 7),
        (36, 46, 6), (164, 46, 6), (86, 96, 5), (114, 96, 5),
    ]
    for (mr, mc, mr_) in mud_specs:
        A4.place_blob(grid, forbid, mr, mc, mr_, MUD, rng, lobes=8, jit=0.30)

    # 8) 土路（8 条，基地东侧向湖）
    for (dr, dc, dr_) in [(28, 42, 7), (76, 42, 7), (124, 42, 7), (172, 42, 7),
                          (52, 66, 5), (148, 66, 5), (52, 134, 5), (148, 134, 5)]:
        A4.place_blob(grid, forbid, dr, dc, dr_, DIRT, rng, lobes=4, jit=0.34)

    # 9) 石地（10 片）
    for (sr_, sc_, srad) in [(50, 40, 7), (150, 40, 7), (50, 160, 7), (150, 160, 7),
                             (100, 75, 6), (100, 125, 6), (36, 110, 5), (164, 110, 5),
                             (76, 90, 5), (124, 90, 5)]:
        A4.place_blob(grid, forbid, sr_, sc_, srad, STONE, rng, lobes=5, jit=0.20)

    # 10) 镜像
    for r in range(H):
        for c in range(100):
            grid[r][199 - c] = grid[r][c]
    # 11) 桥窗深水→浅滩
    for (r0, r1, c0, c1) in BRIDGES:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if grid[r][c] in (WATER, 8, 9):
                    grid[r][c] = SHOAL
    # 12) 出生点清场
    for (sr, sc, _t) in spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 2:
                    if grid[r][c] in (WATER, 8, 9, SHOAL, HIGHSTONE, MUD, HIGHGRASS, DIRT, STONE, SAND):
                        grid[r][c] = GRASS
    A4._clean_water_vertices(grid)
    for r in range(H):
        for c in range(100):
            grid[r][199 - c] = grid[r][c]
    return grid, rng, spawns


def make_decor_dense(grid, rng):
    decor = [[0] * W for _ in range(H)]
    TREE = [890, 891]; ROCK = [718, 719, 754]; TUFT = [711, 712, 714, 898]
    for r in range(H):
        for c in range(W):
            t = grid[r][c]
            if t == HIGHGRASS and rng.random() < 0.60:
                decor[r][c] = 1 + rng.choice(TREE)
            elif t == HIGHSTONE and rng.random() < 0.30:
                decor[r][c] = 1 + rng.choice(ROCK)
            elif t == GRASS and rng.random() < 0.05:
                decor[r][c] = 1 + rng.choice(TUFT)
            elif t == WATER and rng.random() < 0.012:
                decor[r][c] = 1 + rng.choice(ROCK)
    return decor


if __name__ == "__main__":
    # ★ 半独立生成：左右团块位置/半径/类型完全相同（specs 固定 → 战术等价），
    #   但形状相位用不同种子 → 视觉不再是复制粘贴。
    gA, rng, spawns = build_arc_v3(11)
    gB, _, _ = build_arc_v3(29)
    grid = [row[:] for row in gA]
    for r in range(H):
        for c in range(100, W):
            grid[r][c] = gB[r][199 - c]
    # 中轴带平滑：c 96..103 用 A 侧连续值，避免接缝错位
    for r in range(H):
        for c in range(96, 104):
            if c < 100:
                grid[r][c] = gA[r][c]
            else:
                grid[r][c] = gA[r][199 - c]
    for _ in range(8):
        A4._clean_water_vertices(grid)
    P._fix_flower(grid)
    for _ in range(4):
        A4._clean_water_vertices(grid)
    items = [[0] * W for _ in range(H)]
    A4.place_home_mines(items, grid, spawns)
    P.place_node_mines_safe(items, grid, P.mirror_nodes(P.NEUTRAL_8P))
    for r in range(H):                     # 只镜像矿点；地形保持左右形状独立（去对称）
        for c in range(100):
            items[r][199 - c] = items[r][c]
    flower = C.verify_no_flower(grid)
    # 公平性：左右地形占比差异（<=3% 视为等价）
    cl = Counter(grid[r][c] for r in range(H) for c in range(100))
    cr = Counter(grid[r][c] for r in range(H) for c in range(100, W))
    tl, tr = sum(cl.values()), sum(cr.values())
    diff = max(abs(cl[k] / tl - cr[k] / tr) for k in set(cl) | set(cr)) * 100
    mir = round(diff, 2)
    bad, _ = P.bfs_ok(grid, spawns)
    decor = make_decor_dense(grid, rng)
    out = "/workspace/重做地图/纯地形版/圆弧法权8p_有机版V2.tmx"
    issues = P.write_pure(grid, decor, items, spawns, out)
    K.render(out, out.replace(".tmx", "_贴图.png"))
    import gen_analysis_png as AP
    AP.render(out, out.replace(".tmx", "_地形解析.png"), scale=4)
    terr = Counter(v for row in grid for v in row); tot = W * H
    nm = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 7: "水", 8: "海", 9: "洋", 12: "高草", 14: "高石", 23: "浅滩"}
    print("地形占比:", {nm.get(k, k): f"{v*100/tot:.1f}%" for k, v in terr.most_common()})
    print(f"花屏={flower} 镜像失配={mir} 连通断={bad} 矿={sum(sum(r_) for r_ in items)} 校验={issues if issues else '无'}")
