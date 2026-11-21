#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交付前自检脚本（AI 工作流第 2 步用）。
用法：  把本文件放 skill 目录，与 gen_koth.py 同处，然后
        python3 verify.py [out_tmx] [seed] [size] [teams]
默认：   python3 verify.py rw_koth.tmx 7 160 8
全绿（每项括号里"须"的值）才交付。
"""
import sys, os
import numpy as np
import xml.etree.ElementTree as ET
from collections import deque

import gen_koth as G

out = sys.argv[1] if len(sys.argv) > 1 else "/workspace/rw_koth.tmx"
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
size = int(sys.argv[3]) if len(sys.argv) > 3 else 160
teams = int(sys.argv[4]) if len(sys.argv) > 4 else 8

tree, fgmap, spawns, grid, ground, items, decor, issues = G.build_koth(seed, size, teams, out)
g = np.array(grid)
H, W = g.shape

# ① 无孤立浅滩碎斑（浅滩且 Chebyshev 距离 2 内无沙）
s1 = sum(1 for r in range(H) for c in range(W)
         if g[r, c] == 23 and not (g[max(0, r - 2):r + 3, max(0, c - 2):c + 3] == 3).any())

# ② 无 沙↔海/洋 硬切（含海 8 与洋 9）
s2 = sum(1 for r in range(H) for c in range(W) if g[r, c] == 3
         and (g[max(0, r - 1):r + 2, max(0, c - 1):c + 2] == 8).any()
         or (g[max(0, r - 1):r + 2, max(0, c - 1):c + 2] == 9).any())
# 上面的 or 因优先级需重写，下面用稳妥写法
s2 = 0
for r in range(H):
    for c in range(W):
        if g[r, c] == 3:
            blk = g[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
            if (blk == 8).any() or (blk == 9).any():
                s2 += 1

# ③ 8 出生岛连通（陆地+沙桥 BFS）
land = {0, 1, 2, 3, 4, 23}
def nl(sr, sc):
    for rad in range(30):
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                rr, cc = sr + dr, sc + dc
                if 0 <= rr < H and 0 <= cc < W and g[rr, cc] in land:
                    return (rr, cc)
seeds = [nl(*s) for s in spawns]
seen = {seeds[0]}
q = deque(seeds[:1])
while q:
    r, c = q.popleft()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rr, cc = r + dr, c + dc
        if 0 <= rr < H and 0 <= cc < W and g[rr, cc] in land and (rr, cc) not in seen:
            seen.add((rr, cc))
            q.append((rr, cc))
s3 = sum(1 for s in seeds if s in seen)

# ④ tmx 单文件 + 单位
t = ET.parse(out).getroot()
s4 = [e.get("source") for e in t.iter("tileset") if e.get("source")]
uo = t.find("objectgroup[@name='UnitObjects']")
objs = uo.findall("object") if uo is not None else []
s5 = len(objs)
# 中岛 4 水晶：UnitObjects 里 crystalResource 单位，须为 4 个且中立(team=-1)、靠近中心
crystals = []
for o in objs:
    u = o.find("properties/property[@name='unit']")
    if u is not None and u.get("value") == "crystalResource":
        tm = o.find("properties/property[@name='team']")
        crystals.append((int(o.get("y", 0)) // 20, int(o.get("x", 0)) // 20,
                         tm.get("value") if tm is not None else "?"))
cctr = (int(cy) if 'cy' in dir() else size // 2, int(cx) if 'cx' in dir() else size // 2)
# cy/cx 来自 build_koth 的 grid 生成；这里用 size//2 兜底
cc_r, cc_c = size // 2, size // 2
near_center = sum(1 for (r, c, tm) in crystals if max(abs(r - cc_r), abs(c - cc_c)) <= 6 and tm == "-1")
s6 = len(crystals)
s7 = near_center

print(f"碎斑={s1} (须0)")
print(f"沙-海/洋硬切={s2} (须0)")
print(f"连通出生点={s3}/{teams} (须=人数)")
print(f"外部引用 source={s4} (须[])")
print(f"UnitObjects={s5} (须{teams*3+4})")
print(f"中岛 crystalResource 水晶={s6} (须4) | 其中中立且近中心={s7} (须4)")
print("   水晶坐标(行,列,team):", crystals)
ok = (s1 == 0 and s2 == 0 and s3 == teams and s4 == []
      and s5 == teams * 3 + 4 and s6 == 4 and s7 == 4)
print("✅ 全部通过，可交付" if ok else "❌ 有项目不达标，先修地图再交付")
sys.exit(0 if ok else 1)
