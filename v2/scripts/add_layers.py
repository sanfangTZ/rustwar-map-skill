#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_layers.py —— 给 tmx 补齐铁锈战争必需的层（完整可运行）

对应文档：references/image_to_tmx.md  第 4.4 节

铁锈战争强制要求的三个 tile layer（按顺序）：
  1. Ground  地面   ← 地形
  2. Items   项目   ← 纯地形图全填 0
  3. Units   单位   ← 纯地形图全填 0

若地图缺 Items/Units，游戏会报：
  「加载地图错误：项目"层没有在地图中找到，这一层是必需的」

本脚本会自动：
  - 检测已有层
  - 在 Ground 层之后、Triggers 之前补上缺失的 Items/Units 空层
  - 数据块用 base64(gzip(little-endian uint32)) 编码（与游戏一致）

用法：
  python3 add_layers.py <地图.tmx>             # 补齐缺失层（原地，.bak 备份）
  python3 add_layers.py <地图.tmx> --out X.tmx # 输出到新文件
  python3 add_layers.py <地图.tmx> --check     # 只检测不修改

署名：三方同志｜作者交流 QQ 群：528400691
"""
import sys
import re
import gzip
import base64
import struct
import argparse
import shutil

NEEDED = ['Ground', 'Items', 'Units']


def encode_empty(w, h):
    """生成 w*h 个 0 的 base64(gzip(小端 uint32)) 数据块（TMX 折行）。"""
    raw = struct.pack('<%dI' % (w * h), *([0] * (w * h)))
    comp = gzip.compress(raw, 9)
    b64 = base64.b64encode(comp).decode('ascii')
    return '\n'.join(b64[i:i + 76] for i in range(0, len(b64), 76))


def get_layers(raw):
    """返回 [(层名, 起止位置)]，按出现顺序。"""
    out = []
    for m in re.finditer(r'<layer\s+name="([^"]+)"[^>]*>', raw):
        out.append((m.group(1), m.start()))
    return out


def get_size(raw):
    """从 <map> 标签取地图尺寸。

    坑：不能直接对全文用 `<map[^>]*width=` —— `[^>]*` 会吃到
    `tilewidth="20"` 里的 `width=`，导致把地块尺寸当地图尺寸。
    正确做法：先取出 <map ...> 整段，再在段内用 \\b 单词边界匹配。
    """
    m = re.search(r'<map\b[^>]*>', raw)
    if not m:
        raise SystemExit('错误：找不到 <map> 标签')
    tag = m.group(0)

    def attr(name):
        a = re.search(r'\b%s="(\d+)"' % name, tag)
        if not a:
            raise SystemExit('错误：<map> 缺少属性 %s' % name)
        return int(a.group(1))

    return attr('width'), attr('height')


def main():
    ap = argparse.ArgumentParser(description='补齐铁锈战争必需层 Ground/Items/Units')
    ap.add_argument('tmx')
    ap.add_argument('--out', default=None)
    ap.add_argument('--check', action='store_true', help='只检测不修改')
    args = ap.parse_args()

    with open(args.tmx, encoding='utf-8', errors='surrogateescape') as f:
        raw = f.read()

    W, H = get_size(raw)
    print('地图尺寸: %dx%d' % (W, H))

    layers = get_layers(raw)
    present = [n for n, _ in layers]
    print('现有层: %s' % (', '.join(present) or '(无)'))

    missing = [n for n in NEEDED if n not in present]
    if not missing:
        print('[OK] Ground / Items / Units 三层齐全，无需补层')
        return 0

    print('[检测] 缺少: %s' % ', '.join(missing))
    if args.check:
        print('[CHECK] 未修改（--check）')
        return 1

    empty = encode_empty(W, H)

    def make_layer(nm):
        return (
            ' <layer name="%s" width="%d" height="%d">\n'
            '  <data encoding="base64" compression="gzip">\n'
            '%s\n'
            '  </data>\n'
            ' </layer>\n' % (nm, W, H, empty)
        )

    # 插入锚点：最后一个已有层（Ground/Items/Units 之一）的 </layer> 之后
    # 优先插到 Ground 之后；否则插到 </map> 前的 objectgroup 之前
    new = raw
    insert_pos = None
    # 找 Ground 层的 </layer> 结束位置
    mg = re.search(r'<layer\s+name="Ground"[^>]*>.*?</layer>\s*', raw, re.S)
    if mg:
        insert_pos = mg.end()
    else:
        # 退而求其次：插到开层位置之前（</map> 前）
        insert_pos = raw.rfind('</map>')

    block = ''.join(make_layer(n) for n in missing)
    new = raw[:insert_pos] + block + raw[insert_pos:]

    if args.out:
        with open(args.out, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 已写入 %s（补了 %s）' % (args.out, ', '.join(missing)))
    else:
        shutil.copy(args.tmx, args.tmx + '.bak')
        with open(args.tmx, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 原地补齐 %s（补了 %s，.bak 已备份）' % (args.tmx, ', '.join(missing)))

    # 复核
    newlayers = [n for n, _ in get_layers(new)]
    print('[复核] 现在层: %s' % ', '.join(newlayers))
    return 0


if __name__ == '__main__':
    sys.exit(main())