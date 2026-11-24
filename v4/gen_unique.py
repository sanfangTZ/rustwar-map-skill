#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图三~图八：区域化重做（整体骨构各异 + 地形主色各异）"""
import os, sys, math, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import gen_pure_all as P
import gen_4v4_arena as A4
import gen_combined as C
from collections import Counter

W = H = P.W
GRASS, DIRT, SAND, MUD = A4.GRASS, A4.DIRT, A4.SAND, A4.MUD
SHOAL, WATER, HIGHGRASS, HIGHSTONE = A4.SHOAL, A4.WATER, A4.HIGHGRASS, A4.HIGHSTONE


def blank():
    return [[GRASS] * W for _ in range(H)]

def wall_h(grid, r, c0, c1, th=3):
    for rr in range(r - th, r + th + 1):
        for cc in range(c0, c1 + 1):
            if 0 <= rr < H and 0 <= cc < W:
                grid[rr][cc] = HIGHSTONE

def wall_v(grid, c, r0, r1, th=3):
    for cc in range(c - th, c + th + 1):
        for rr in range(r0, r1 + 1):
            if 0 <= rr < H and 0 <= cc < W:
                grid[rr][cc] = HIGHSTONE

def gate_h(grid, r, c0, c1, th=3):
    for rr in range(r - th, r + th + 1):
        for cc in range(c0, c1 + 1):
            if 0 <= rr < H and 0 <= cc < W:
                grid[rr][cc] = GRASS

def oval_lake(grid, cy, cx, R, ky, rng, jit=0.10):
    amp = jit * R
    for r in range(H):
        for c in range(W):
            d = math.hypot((r - cy) / ky, c - cx) + amp * A4._noise(r, c)
            if d <= R:
                grid[r][c] = WATER
            elif d <= R + 2:
                grid[r][c] = SHOAL
            elif d <= R + 6:
                grid[r][c] = SAND

def paint(grid, cat, cond, only=GRASS):
    for r in range(H):
        for c in range(W):
            if grid[r][c] == only and cond(r, c):
                grid[r][c] = cat

def scatter(grid, rng, specs, spawns):
    forbid = [[1 if grid[r][c] in (WATER, 8, 9, SHOAL, SAND) else 0 for c in range(W)] for r in range(H)]
    for (sr, sc, _t) in spawns:
        for dr in range(-4, 5):
            for dc in range(-4, 5):
                rr, cc = sr + dr, sc + dc
                if 0 <= rr < H and 0 <= cc < W:
                    forbid[rr][cc] = 1
    for cat, lst in specs:
        for (cr, cc, rad) in lst:
            A4.place_blob(grid, forbid, cr, cc, rad, cat, rng, lobes=8, jit=0.28)

def finish(grid, spawns):
    P._spawn_protect(grid, spawns)
    for _ in range(6):
        A4._clean_water_vertices(grid)
    P._fix_flower(grid)
    for _ in range(4):
        A4._clean_water_vertices(grid)
    return grid


def build_lines(seed, spawns):
    rng = random.Random(seed); grid = blank()
    for (sr, sc, _t) in spawns:
        side = 1 if sc < 100 else -1
        wall_v(grid, sc - side * 9, sr - 11, sr + 11, th=2)
        gate_h(grid, sr, sc - side * 9 - 2, sc - side * 9 + 2, th=2)
    for (wr, gc) in ((58, (42, 96, 154)), (100, (42, 96, 154)), (142, (42, 96, 154))):
        wall_h(grid, wr, 0, 199, th=4)
        for c0 in gc:
            gate_h(grid, wr, c0, c0 + 6, th=4)
    for (rr, cc) in ((80, 68), (80, 132), (120, 68), (120, 132)):
        A4.place_blob(grid, [[0] * W for _ in range(H)], rr, cc, 5, HIGHSTONE, rng, lobes=6, jit=0.2)
    scatter(grid, rng, [(HIGHGRASS, [(34, 66, 8), (166, 66, 8), (34, 134, 8), (166, 134, 8),
                                      (78, 58, 7), (122, 142, 7), (78, 142, 7), (122, 58, 7)]),
                        (MUD, [(88, 40, 7), (112, 160, 7), (30, 100, 6), (170, 100, 6)]),
                        (A4.STONE, [(70, 50, 6), (130, 150, 6), (100, 100, 7)])], spawns)
    return finish(grid, spawns), rng, spawns


def build_sriver(seed, spawns):
    rng = random.Random(seed); grid = blank()
    oval_lake(grid, 100.0, 99.5, 26, 3.2, rng, jit=0.12)
    A4.carve_islands(grid, [(45.0, 99.5, 5, 3), (100.0, 99.5, 6, 3), (155.0, 99.5, 5, 3)])
    for (r0, r1) in ((20, 28), (62, 70), (96, 104), (130, 138), (176, 184)):
        P._force_shoal(grid, r0, r1, 62, 138)
    scatter(grid, rng, [(HIGHSTONE, [(20, 20, 9), (180, 20, 9), (20, 178, 9), (180, 178, 9)]),
                        (HIGHGRASS, [(60, 40, 8), (140, 40, 8), (60, 160, 8), (140, 160, 8)]),
                        (MUD, [(100, 30, 7), (100, 170, 7)])], spawns)
    return finish(grid, spawns), rng, spawns


def build_ringfort(seed, spawns):
    rng = random.Random(seed); grid = blank()
    cy, cx = 100.0, 99.5
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cy, c - cx)
            if 50 <= d <= 56:
                if abs(r - cy) <= 4 or abs(c - cx) <= 4:
                    grid[r][c] = GRASS
                else:
                    grid[r][c] = HIGHSTONE
    A4.build_lake(grid, cy, cx, 16, rng, phase=rng.uniform(0, 6), jit=0.16)
    A4.carve_islands(grid, [(cy, cx, 6, 3)])
    paint(grid, A4.STONE, lambda r, c: 57 <= math.hypot(r - cy, c - cx) <= 70)
    paint(grid, HIGHGRASS, lambda r, c: (math.hypot(r - 16, c - 16) < 22 or math.hypot(r - 16, c - 184) < 22
                                          or math.hypot(r - 184, c - 16) < 22 or math.hypot(r - 184, c - 184) < 22))
    return finish(grid, spawns), rng, spawns


def build_maze(seed, spawns):
    rng = random.Random(seed); grid = blank()
    LAKES = [(58, 56, 17), (58, 143, 17), (142, 56, 17), (142, 143, 17), (100, 99.5, 19)]
    for (cy, cx, R) in LAKES:
        oval_lake(grid, float(cy), float(cx), R, 1.0, rng, jit=0.10)
    for (r, c) in ((58, 99), (142, 99), (99, 58), (99, 143)):
        P._force_shoal(grid, r - 4, r + 4, c - 14, c + 14)
    def far_from_lakes(r, c):
        return min(math.hypot(r - ly, c - lx) - LR for (ly, lx, LR) in LAKES) >= 9
    paint(grid, MUD, far_from_lakes)
    paint(grid, HIGHGRASS, lambda r, c: r <= 12 or r >= 187)
    return finish(grid, spawns), rng, spawns


def build_yrift(seed, spawns):
    rng = random.Random(seed); grid = blank()
    cy, cx = 100.0, 99.5
    for ang in (math.radians(90), math.radians(210), math.radians(330)):
        ux, uy = math.cos(ang), math.sin(ang)
        px, py = -uy, ux
        for t in range(0, 105):
            r0 = cy + uy * t; c0 = cx + ux * t
            for w in range(-11, 12):
                rr = int(round(r0 + py * w)); cc = int(round(c0 + px * w))
                if not (0 <= rr < H and 0 <= cc < W):
                    continue
                aw = abs(w)
                if aw <= 4:
                    grid[rr][cc] = GRASS
                elif aw <= 9:
                    grid[rr][cc] = HIGHSTONE
    paint(grid, SAND, lambda r, c: True)
    paint(grid, A4.STONE, lambda r, c: (r * 7 + c * 13) % 97 < 6)
    return finish(grid, spawns), rng, spawns


def build_ruins(seed, spawns):
    rng = random.Random(seed); grid = blank()
    cy, cx = 100.0, 99.5
    for (rad, doors) in ((24, (90, 270)), (44, (45, 225)), (64, (0, 180))):
        for r in range(H):
            for c in range(W):
                d = math.hypot(r - cy, c - cx)
                if rad - 1.5 <= d <= rad + 1.5:
                    ang = math.degrees(math.atan2(r - cy, c - cx)) % 360
                    if any(abs((ang - a + 180) % 360 - 180) <= 7 for a in doors):
                        continue
                    grid[r][c] = HIGHSTONE
    A4.carve_islands(grid, [(cy, cx, 7, 3)])
    paint(grid, HIGHGRASS, lambda r, c: True)
    paint(grid, A4.STONE, lambda r, c: 66 <= math.hypot(r - cy, c - cx) <= 74)
    return finish(grid, spawns), rng, spawns


if __name__ == "__main__":
    jobs = [("双湖桥8p", build_lines, 51), ("大河流两岸8p", build_sriver, 52),
            ("铁臂山系8p", build_ringfort, 53), ("混沌大陆8p", build_maze, 54),
            ("伍分裂谷10p", build_yrift, 55), ("失落圣坛10p", build_ruins, 56)]
    for name, fn, sd in jobs:
        spawns = P.get_spawns5() if "10p" in name else A4.get_spawns()
        grid, rng, spawns = fn(sd, spawns)
        ok = P.make(name, grid, rng, spawns, P.NEUTRAL_10P if "10p" in name else P.NEUTRAL_8P)
        print(f"{'OK ' if ok else 'FAIL'} {name}")
