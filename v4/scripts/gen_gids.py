#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 tmx 地图【地形格 -> gid】渲染器

原理: 顶点模型。每格 tile 的四角，各由"该角周围 2x2 格地形"多数投票决定
      (平票取较小地形值)。再从图集字典反向查表得到 gid。

用法:
    python3 gen_gids.py <grid_terrain.json> <gids_out.json> [ground_dict.json]

输出:
    精确(直接命中): N   模糊(回退): M   最大汉明距离: K
    (理想: 精确=10000, 模糊=0)

判定:
    模糊回退 > 0  => 布局有"某格四邻 > 2 种地形"，请回去加隔离带 / 跑迭代修复器。
"""
import sys
import json
import collections


def sample(terr, vx, vy, W, H):
    """顶点 (vx,vy) 周围 2x2 格多数投票（平票取小）"""
    cells = []
    for dy in (-1, 0):
        for dx in (-1, 0):
            x, y = vx + dx, vy + dy
            if 0 <= x < W and 0 <= y < H:
                cells.append(terr[y][x])
    if not cells:
        return 0
    cnt = collections.Counter(cells)
    return max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))[0]


def build_comb(ground_dict_path):
    """从图集字典建 (tl,tr,bl,br) -> [gid,...] 反查表

    注意: ground_dict.json 的 key 是【0 基图集索引】，
          而 TMX 里真实 gid = 索引 + 1（gid 0 表示空，实际 tile 从 1 开始）。
          所以这里 append 时统一 +1，输出即可直接被游戏识别。
    """
    D = json.load(open(ground_dict_path, encoding='utf-8'))
    comb = {}
    for gid_s, v in D.get('tiles', {}).items():
        t = v.get('terrain') if isinstance(v, dict) else v
        if t and len(t) == 4:
            comb.setdefault(tuple(t), []).append(int(gid_s) + 1)
    return comb


def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def main():
    if len(sys.argv) < 3:
        print('用法: python3 gen_gids.py <grid_terrain.json> <gids_out.json> [ground_dict.json]')
        sys.exit(1)
    grid_path = sys.argv[1]
    out_path = sys.argv[2]
    gd_path = sys.argv[3] if len(sys.argv) > 3 else 'ground_dict.json'

    terr = json.load(open(grid_path, encoding='utf-8'))
    H = len(terr)
    W = len(terr[0])
    comb = build_comb(gd_path)

    out = [[0] * W for _ in range(H)]
    exact = fuzzy = 0
    max_ham = 0
    for y in range(H):
        for x in range(W):
            tl = sample(terr, x,     y,     W, H)
            tr = sample(terr, x + 1, y,     W, H)
            bl = sample(terr, x,     y + 1, W, H)
            br = sample(terr, x + 1, y + 1, W, H)
            key = (tl, tr, bl, br)
            if key in comb:
                out[y][x] = comb[key][0]
                exact += 1
            else:
                best, bd = None, 9
                for k, gs in comb.items():
                    d = hamming(k, key)
                    if d < bd:
                        bd, best = d, gs[0]
                out[y][x] = best
                fuzzy += 1
                max_ham = max(max_ham, bd)

    json.dump(out, open(out_path, 'w'), ensure_ascii=False)
    used = set(x for row in out for x in row)
    print('精确(直接命中): %d  模糊(回退): %d  最大汉明距离: %d'
          % (exact, fuzzy, max_ham))
    print('命中 quad 模式数: %d  实用 gid 种类: %d' % (len(comb), len(used)))
    print('saved', out_path)
    if fuzzy:
        print('!! 有 %d 格回退渲染，建议回布局阶段加隔离带' % fuzzy)


if __name__ == '__main__':
    main()