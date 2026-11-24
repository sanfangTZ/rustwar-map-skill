#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 1.15 —— 『地面层整合.tsx』整合图集的自动拼接与特征放置

该 tsx 是 RW 的完整地面图集（36 列 × 1080 格），每个 tile 带
terrain="TL,TR,BL,BR" 四角地形索引 + 可选属性(cliff/water/trees/lava)。
本模块用 Tiled 的「四角对角线」自动拼接规则：
  某格四角地形 = 其 西北/东北/西南/东南 四个对角邻居的地形类别。
  选 terrain 属性与该四角签名完全匹配的 tile；匹配不到则用该地形纯 interior 块。

地形角索引(来自 terraintypes)：
  0草 1土 2石 3沙 4泥 5雪 6冰 7水 8海 9洋 11岩浆 23浅滩
  12高草 14高石 26短草 27透明背景岩石 28岩石 29枯木 30冰刺 ...
"""
import os, math, re, random
from collections import Counter
import numpy as np
import xml.etree.ElementTree as ET
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TSX = os.path.join(HERE, "地面层整合.tsx")
PNG = os.path.join(HERE, "地面层整合.png")

# 角索引 -> 名称
TERRAIN_NAMES = ["草", "土", "石", "沙", "泥", "雪", "冰", "水", "海", "洋",
                 "闪烁冰碴", "岩浆", "高草", "高土", "高石", "高沙", "高泥", "高雪",
                 "坡上草", "坡上沙", "坡上雪", "坡上土", "坡下图", "浅滩",
                 "草中树", "雪中树", "短草", "透明背景岩石", "岩石", "枯木", "冰刺"]

# 类别名 -> 角索引
CAT = {
    "grass": 0, "dirt": 1, "stone": 2, "sand": 3, "mud": 4, "snow": 5, "ice": 6,
    "water": 7, "sea": 8, "ocean": 9, "lava": 11, "shoal": 23,
    "tallgrass": 12, "shortgrass": 26,
}

_TILES = {}      # tid -> (corners tuple) or None
_PURE = {}       # 角索引 -> [纯 interior tile id]
_SIG = {}        # corners tuple -> tid
_DECOR = []      # 装饰 overlay tile id（透明背景：岩石/枯木/树）
_COLS = 36
_COUNT = 1080


def _load():
    global _TILES, _PURE, _SIG, _DECOR, _COLS, _COUNT
    root = ET.parse(TSX).getroot()
    _COLS = int(root.get("columns"))
    _COUNT = int(root.get("tilecount"))
    for t in root.findall("tile"):
        tid = int(t.get("id"))
        terr = t.get("terrain")
        corners = tuple(int(x) for x in terr.split(",")) if terr else None
        _TILES[tid] = corners
        if corners is not None:
            _SIG[corners] = tid
            if len(set(corners)) == 1:
                _PURE.setdefault(corners[0], []).append(tid)
    # 装饰 overlay：无地形角(即透明背景道具) 或 已知岩石/枯木/树
    im = np.array(Image.open(PNG).convert("RGBA"))
    TW = TH = 20

    def arr(tid):
        r = tid // _COLS; c = tid % _COLS
        return im[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW]
    known = {826: "岩石", 718: "透明背景岩石", 934: "枯木", 499: "草中树", 502: "雪中树", 1042: "冰刺"}
    for tid, corners in _TILES.items():
        a = arr(tid)[:, :, 3]
        cov = (a >= 40).mean()
        if tid in known:
            _DECOR.append(tid)
            continue
        # 无角属性且为半透明道具（非全空、非全实）
        if corners is None and 0.25 < cov < 0.97:
            rgb = arr(tid)[:, :, :3].astype(int)[a >= 40]
            if len(rgb) == 0:
                continue
            rg = np.median(rgb[:, 0]); gg = np.median(rgb[:, 1]); bg = np.median(rgb[:, 2])
            # 灰白=岩石类；褐=枯木类；绿=草树类
            if (rg > 110 and gg > 110 and bg > 110) or (rg > bg + 15 and gg < rg + 20) or (gg > rg + 10):
                _DECOR.append(tid)


_load()


_SIM = {9: 7, 8: 7, 23: 3, 4: 1, 2: 1, 12: 0, 26: 0}   # 相似类别链（fallback 用）


def _sim_chain(v):
    chain = [v]
    while chain[-1] in _SIM:
        chain.append(_SIM[chain[-1]])
    return chain


def autotile(cat_grid):
    """cat_grid: 每格为地形角索引(int)。返回 tile id 二维列表（用于 ground 层）。

    标准 Tiled 四角拼接：先建全局「角点」地形矩阵 (H+1)x(W+1)。
    角点 (i,j) 由共享它的 4 格 (i-1,j-1)/(i-1,j)/(i,j-1)/(i,j) 多数投票决定；
    平局取首个最大（规则与使用它的格子无关，保证相邻格对同一角点取值一致，
    过渡才能严丝合缝）。然后每格 sig=(corner[r][c],corner[r][c+1],
    corner[r+1][c],corner[r+1][c+1]) 查 _SIG；查不到按 _SIM 相似链替换角
    （替换步数最少优先）保住过渡块；仍无才用纯 interior 块。"""
    H = len(cat_grid); W = len(cat_grid[0])

    def cell(rr, cc):
        if 0 <= rr < H and 0 <= cc < W:
            return cat_grid[rr][cc]
        return None  # 地图外不算票

    # 1) 全局角点矩阵
    corner = [[0] * (W + 1) for _ in range(H + 1)]
    for i in range(H + 1):
        for j in range(W + 1):
            votes = [v for v in (cell(i - 1, j - 1), cell(i - 1, j),
                                 cell(i, j - 1), cell(i, j)) if v is not None]
            if not votes:
                corner[i][j] = cell(0, 0) or 0
                continue
            cnt = {}
            for v in votes:
                cnt[v] = cnt.get(v, 0) + 1
            best = max(cnt.values())
            top = [k for k, vv in cnt.items() if vv == best]
            corner[i][j] = top[0]          # 平局取首个最大（确定、全局一致）

    # 2) 逐格按四角签名选 tile
    out = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            cat = cat_grid[r][c]
            sig = (corner[r][c], corner[r][c + 1], corner[r + 1][c], corner[r + 1][c + 1])
            tid = _SIG.get(sig)
            if tid is None:
                chains = [_sim_chain(v) for v in sig]
                best = None
                for combo in _product48(chains):
                    steps = sum(combo)
                    if best is not None and steps >= best[0]:
                        continue
                    s2 = tuple(ch[i] for ch, i in zip(chains, combo))
                    t = _SIG.get(s2)
                    if t is not None:
                        best = (steps, t)
                tid = best[1] if best else None
            if tid is None:
                pl = _PURE.get(cat)
                tid = pl[0] if pl else 0
            out[r][c] = tid
    return out


def _product48(chains):
    """笛卡尔积（每条链最多 3 项，最多 81 组合），按替换步数升序产出。"""
    combos = [()]
    for ch in chains:
        combos = [c + (i,) for c in combos for i in range(len(ch))]
    combos.sort(key=sum)
    return combos


# ---------------------------------------------------------------------------
# 修边诊断（只诊断，不强制对称）：
#   修边的真标准是【零花屏】= 两半各自 autotile 都能干净渲染；不是像素级镜像。
#   ★ 血泪教训（勿再犯）：本 tsx 的"交换左右角的 tile"≠"像素级水平翻转"（实测匹配率仅 0.9%）。
#     因此"复制镜像"与"翻转镜像(交换角)"都会把右半过渡贴错 → 右半全花。
#     Rusted Warfare 瓦片不支持逐格翻转，故本图集无法靠贴图做到像素级镜像；
#     正确做法永远是：让 autotile 按地形自然渲染，用 verify_no_flower 卡零花屏即可。
# ---------------------------------------------------------------------------
_PAINT = {0, 1, 2, 3, 4, 7, 8, 9, 12, 14, 23}   # 草/土/石/沙/泥/水/海/洋/高草/高石/浅滩


def edge_metrics(cat_grid, paint=None):
    """修边质量量化（references/edge_cleanup.md §J.2，与 gen_5v5_common.edge_metrics 同口径）。

    逐内格检查 8 邻同类数 cnt：
      iso   = cnt<3  （孤立尖刺/1 格颈）
      cnt0  = cnt==0 （完全悬空）
      diagonly = 正交无同类但对角有（"仅对角相连"伪影）
    返回值越低越好。这是 skill 判定"修边有没有整好"的权威指标。"""
    if paint is None:
        paint = _PAINT
    H = len(cat_grid)
    W = len(cat_grid[0])
    iso = cnt0 = diagonly = 0
    ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
    DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            cat = cat_grid[r][c]
            if cat not in paint:
                continue
            orth = [cat_grid[r + dr][c + dc] for dr, dc in ORTH]
            diag = [cat_grid[r + dr][c + dc] for dr, dc in DIAG]
            cnt = sum(1 for x in orth + diag if x == cat)
            if cnt < 3:
                iso += 1
            if cnt == 0:
                cnt0 += 1
            if cat not in orth and any(x == cat for x in diag):
                diagonly += 1
    return iso, cnt0, diagonly


def edge_pass_rate(cat_grid, paint=None):
    """修边正确率（%）。bad=iso+cnt0+diagonly，内部可检格=(H-2)*(W-2)。

    skill 硬门槛 98%（gen_5v5_common.edge_auto_fix）；本修边补丁要求对称竞技图 ≥99.5%，
    且镜像不对称必须为 0，才能"零差错"出图。"""
    iso, cnt0, diagonly = edge_metrics(cat_grid, paint)
    H = len(cat_grid)
    interior = max(1, (H - 2) * (H - 2))
    bad = iso + cnt0 + diagonly
    return 100.0 * (1 - bad / interior), iso, cnt0, diagonly


def verify_no_flower(cat_grid):
    """真·修边硬门槛：检测会导致渲染花屏的 2×2 块，返回违规块数（须为 0）。

    判定：把水族(水7/海8/洋9/浅滩23)归一为同一类（它们互相邻接靠 water-bridge 渲染、合法），
    若某 2×2 块内出现 >2 种不同地形类 → autotile 四角无干净过渡 → 必花屏。
    ★ 注意：这不是"≤1 非草/2×2"那种过严口径（会把水+浅滩+草误判）；也不是要求对称。
    这是"修边有没有整好"的客观底线——只要它=0，两半都渲染干净，与是否镜像对称无关。"""
    H = len(cat_grid)
    W = len(cat_grid[0])
    WAT = {7, 8, 9, 23}

    def canon(t):
        return 70 if t in WAT else t

    bad = 0
    for r in range(H - 1):
        for c in range(W - 1):
            s = {canon(cat_grid[r][c]), canon(cat_grid[r][c + 1]),
                 canon(cat_grid[r + 1][c]), canon(cat_grid[r + 1][c + 1])}
            if len(s) > 2:
                bad += 1
    return bad


def rock_tiles(n=1):
    """返回 n 个装饰岩石/枯木 tile id（随机取自 _DECOR）。"""
    if not _DECOR:
        return []
    return [random.Random().choice(_DECOR) for _ in range(n)]


def info():
    return {
        "count": _COUNT, "cols": _COLS,
        "pure": {TERRAIN_NAMES[k]: len(v) for k, v in _PURE.items()},
        "decor": _DECOR,
    }


if __name__ == "__main__":
    print(info())
