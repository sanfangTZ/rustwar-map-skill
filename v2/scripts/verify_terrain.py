#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 tmx 地图【地形】三重校验脚本

用法:
    python3 verify_terrain.py <tmx路径> [grid_terrain.json]

会输出:
  [1] XML 是否合法
  [2] Ground 层格数 + gid 范围
  [3] 出生点中心 3x3 是否纯草
  [4] 四角地形组合种类数（从 grid 统计；缺失 grid 时跳过）
  [5] 纯块统计（草/石/水/岩浆）
  [6] 采样合规：2x2 顶点 >2 种地形 的格数（应为 0）

退出码: 0=PASS, 1=有需人工复核项
"""
import sys
import re
import json
import base64
import gzip
import struct
import collections
import xml.etree.ElementTree as ET

GRASS_GID = 38          # 纯草 gid（本图集约定，可改）
SPAWNS = [(3, 3), (3, 96), (96, 96), (96, 3)]


def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def decode_ground(s):
    """解出 Ground 层的 gid 二维数组"""
    m = re.search(r'<layer name="Ground"[^>]*>.*?<data[^>]*>(.*?)</data>', s, re.S)
    if not m:
        raise RuntimeError('未找到 Ground 层')
    raw = gzip.decompress(base64.b64decode(m.group(1).strip()))
    flat = list(struct.unpack('<%dI' % (len(raw) // 4), raw))
    mm = re.search(r'<layer name="Ground"[^>]*width="(\d+)"[^>]*height="(\d+)"', s)
    W = int(mm.group(1)); H = int(mm.group(2))
    return [flat[y * W:(y + 1) * W] for y in range(H)], W, H


def sample(terr, vx, vy, W, H):
    """顶点 (vx,vy) 周围 2x2 格多数投票（平票取小）—— 与渲染器逻辑一致"""
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


def gid_to_tid_map(ground_dict_path='ground_dict.json'):
    """gid -> 四角地形列表；优先反查图集字典"""
    try:
        D = json.load(open(ground_dict_path, encoding='utf-8'))
    except Exception:
        return None
    m = {}
    for gid_s, v in D.get('tiles', {}).items():
        t = v.get('terrain') if isinstance(v, dict) else v
        if t and len(t) == 4:
            m[int(gid_s)] = t
    return m or None


def main():
    if len(sys.argv) < 2:
        print('用法: python3 verify_terrain.py <tmx路径> [grid_terrain.json]')
        sys.exit(1)
    tmx = sys.argv[1]
    grid_path = sys.argv[2] if len(sys.argv) > 2 else None

    s = load(tmx)
    print('文件:', tmx)
    print('字节数:', len(s.encode('utf-8')))
    ok_all = True

    # [1] XML
    try:
        ET.fromstring(s)
        print('[1] XML 合法: OK')
    except Exception as e:
        print('[1] XML 合法: FAIL ->', e); ok_all = False

    # [2] Ground
    g, W, H = decode_ground(s)
    flat = [x for row in g for x in row]
    print('[2] Ground 格数: %d  尺寸: %dx%d  gid 范围: %d ~ %d'
          % (len(flat), W, H, min(flat), max(flat)))
    if len(flat) != W * H or len(flat) != 10000:
        print('    !! 格数异常'); ok_all = False

    # [3] 出生点 3x3 纯草
    bad_sp = 0
    for (cx, cy) in SPAWNS:
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                x, y = cx + dx, cy + dy
                if 0 <= x < W and 0 <= y < H and g[y][x] != GRASS_GID:
                    bad_sp += 1
    print('[3] 出生点中心 3x3 纯草: %s' % ('OK' if bad_sp == 0 else ('有 %d 格非草' % bad_sp)))
    if bad_sp:
        ok_all = False

    # [4] 从 grid 统计四角地形组合
    if grid_path:
        try:
            terr = json.load(open(grid_path, encoding='utf-8'))
            combos = set()
            for y in range(H):
                for x in range(W):
                    tl = sample(terr, x,   y,   W, H)
                    tr = sample(terr, x+1, y,   W, H)
                    bl = sample(terr, x,   y+1, W, H)
                    br = sample(terr, x+1, y+1, W, H)
                    combos.add((tl, tr, bl, br))
            print('[4] 四角地形组合种类数: %d' % len(combos))
        except Exception as e:
            print('[4] 读取 grid 失败:', e)
    else:
        print('[4] 未提供 grid_terrain.json，跳过四角组合统计')

    # [5] 纯块统计（从真实地形数组统计各大地形格数）
    #     说明: ground_dict.json 的 tiles[gid]['terrain'] 是【四角局部编号】，
    #           不是草/石/水分类，不能直接当纯度统计（旧版误用，已修正）。
    #           要统计真实地形分布，应使用 grid_terrain.json 的整格地形值。
    TERR_NAME = {0: '草', 2: '石', 7: '水', 11: '岩浆', 14: '高石'}
    if grid_path:
        try:
            terr = json.load(open(grid_path, encoding='utf-8'))
            cnt = collections.Counter(x for row in terr for x in row)
            parts = []
            for tid, cntv in cnt.most_common():
                parts.append('%s(%d)=%d' % (TERR_NAME.get(tid, '?'), tid, cntv))
            print('[5] 地形分布(来自 grid): ' + '  '.join(parts))
        except Exception as e:
            print('[5] 读取 grid 失败:', e)
    else:
        print('[5] 未提供 grid_terrain.json，跳过地形分布统计')

    # [6] 采样合规：2x2 顶点 >2 种地形
    if grid_path:
        try:
            terr = json.load(open(grid_path, encoding='utf-8'))
            bad = 0
            for vy in range(H + 1):
                for vx in range(W + 1):
                    seen = set()
                    for dy in (-1, 0):
                        for dx in (-1, 0):
                            x, y = vx + dx, vy + dy
                            if 0 <= x < W and 0 <= y < H:
                                seen.add(terr[y][x])
                    if len(seen) > 2:
                        bad += 1
            print('[6] 2x2 顶点 >2 种地形: %d' % bad)
            if bad:
                ok_all = False
        except Exception as e:
            print('[6] 检查失败:', e)

    print('\n==> 总体: %s' % ('PASS' if ok_all else '需人工复核'))
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
