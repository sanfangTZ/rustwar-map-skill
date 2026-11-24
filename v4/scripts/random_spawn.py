#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
random_spawn.py —— 一键注入「三格抽签」随机刷兵（完整可运行）

对应文档：references/random_spawn_recipe.md

原理：1 个抽签器(unitAdd+offsetRandomX) 把信标随机撒到 3 格之一，
      每格一个探测器(unitDetect)，抽中就激活该格的出兵器(unitAdd)，
      每格出兵器直接刷「一对组合」→ 保证必出 2 种兵、各 2 个。

用法：
  python3 random_spawn.py <地图.tmx> \
      --cell1 "tank*2,experimentalHoverTank*2" \
      --cell2 "experimentalHoverTank*2,fireBee*2" \
      --cell3 "fireBee*2,tank*2" \
      [--team-out 1] [--team-lot -2] [--delay 30s] \
      [--x-lot 200] [--y-lot 2620] [--out-x 1300] [--out-y 1240] \
      [--id-base 2004] [--prefix lot] [--dry-run] [--out 新地图.tmx]

不传 --out 则原地注入（会先备份 .bak）。
署名：三方同志｜作者交流 QQ 群：528400691
"""
import sys
import re
import argparse
import shutil


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '"'))


def build_objects(prefix, base, cell1, cell2, cell3,
                  team_out, team_lot, delay,
                  x_lot, y_lot, out_x, out_y):
    o = []
    # ① 抽签器
    o.append(
        '  <object id="%d" name="%s_g_ticket" type="unitAdd" '
        'x="%d" y="%d" width="20" height="20">\n'
        '    <properties>\n'
        '      <property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/>\n'
        '      <property name="team" value="%d"/>\n'
        '      <property name="delay" value="%s"/>\n'
        '    </properties>\n'
        '  </object>\n' % (base, prefix, x_lot, y_lot, team_lot, esc(delay)))

    # ②③④ 探测器（覆盖 [x_lot-80, x_lot+120] 三格）
    det_x = [x_lot - 80, x_lot, x_lot + 80]
    for i, dx in enumerate(det_x, 1):
        o.append(
            '  <object id="%d" name="%s_cell%d_det" type="unitDetect" '
            'x="%d" y="%d" width="40" height="40">\n'
            '    <properties>\n'
            '      <property name="unitType" value="mechMissile"/>\n'
            '      <property name="team" value="%d"/>\n'
            '      <property name="minUnits" value="1"/>\n'
            '    </properties>\n'
            '  </object>\n' % (base + i, prefix, i, dx, y_lot, team_lot))

    # ⑤⑥⑦ 出兵器（用 activatedBy 绑定探测器）
    for i, combo in enumerate([cell1, cell2, cell3], 1):
        o.append(
            '  <object id="%d" name="%s_cell%d_add" type="unitAdd" '
            'x="%d" y="%d" width="20" height="20">\n'
            '    <properties>\n'
            '      <property name="spawnUnits" value="%s"/>\n'
            '      <property name="team" value="%d"/>\n'
            '      <property name="activatedBy" value="%s_cell%d_det"/>\n'
            '    </properties>\n'
            '  </object>\n' % (base + 3 + i, prefix, i, out_x, out_y,
                              esc(combo), team_out, prefix, i))
    return ''.join(o)


def main():
    ap = argparse.ArgumentParser(description='一键注入三格抽签随机刷兵')
    ap.add_argument('tmx')
    ap.add_argument('--cell1', required=True, help='第1格出兵组合')
    ap.add_argument('--cell2', required=True)
    ap.add_argument('--cell3', required=True)
    ap.add_argument('--team-out', type=int, default=1)
    ap.add_argument('--team-lot', type=int, default=-2)
    ap.add_argument('--delay', default='30s')
    ap.add_argument('--x-lot', type=int, default=200)
    ap.add_argument('--y-lot', type=int, default=2620)
    ap.add_argument('--out-x', type=int, default=1300)
    ap.add_argument('--out-y', type=int, default=1240)
    ap.add_argument('--id-base', type=int, default=2004)
    ap.add_argument('--prefix', default='lot')
    ap.add_argument('--out', default=None, help='输出路径；不传则原地注入')
    ap.add_argument('--dry-run', action='store_true', help='只打印不写入')
    args = ap.parse_args()

    with open(args.tmx, encoding='utf-8', errors='surrogateescape') as f:
        raw = f.read()

    ans = raw.rfind('</objectgroup>')
    if ans < 0:
        print('[FAIL] 找不到 </objectgroup>（地图无 Triggers 段？）')
        return 1

    block = build_objects(args.prefix, args.id_base, args.cell1, args.cell2, args.cell3,
                          args.team_out, args.team_lot, args.delay,
                          args.x_lot, args.y_lot, args.out_x, args.out_y)

    new = raw[:ans] + block + raw[ans:]
    m = re.search(r'nextobjectid="(\d+)"', new)
    if m:
        nid = max(int(m.group(1)), args.id_base + 7)
        new = re.sub(r'nextobjectid="\d+"', 'nextobjectid="%d"' % nid, new)

    if args.dry_run:
        print(block)
        print('[DRY-RUN] 未写入')
        return 0

    if args.out:
        with open(args.out, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 已写入 %s（%d 字节）' % (args.out, len(new.encode('utf-8'))))
    else:
        shutil.copy(args.tmx, args.tmx + '.bak')
        with open(args.tmx, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 原地注入 %s（.bak 已备份，%d 字节）' % (args.tmx, len(new.encode('utf-8'))))
    print('     注入 7 对象：1 抽签器 + 3 探测器 + 3 出兵器')
    return 0


if __name__ == '__main__':
    sys.exit(main())
