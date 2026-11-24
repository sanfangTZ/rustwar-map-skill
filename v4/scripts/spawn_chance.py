#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spawn_chance.py —— spawnChance 概率刷兵 注入器 + 概率模拟器（完整可运行）

对应文档：references/spawn_chance_recipe.md

铁锈引擎行为：同一 unitAdd 的 spawnUnits 里逗号分隔多个单位时，
引擎会「按顺序逐个撑骰」，每个单位独立判定 spawnChance，
但会累积计数并被 maxSpawnLimit 卡上限。

因此真实出场率 = 自身 spawnChance × 前面所有单位都失败的概率。

用法：
  # ① 只算概率分布（不写文件）
  python3 spawn_chance.py --units "mechminigun*1@0.5,mechflame*1@0.4:1,mechlightning*1@1.0:1"

  # ② 注入到地图
  python3 spawn_chance.py <地图.tmx> --name reward_combo \
      --units "mechminigun*1@0.5,mechflame*1@0.4:1,mechlightning*1@1.0:1" \
      [--x 1300] [--y 1240] [--team 1] [--delay 5s] [--activated-by lot_cell1_det] \
      [--id 2100] [--out 新地图.tmx]

单位语法：unitName*count@spawnChance:maxSpawnLimit
  - *count           可选，默认 1
  - @spawnChance     可选，默认 1.0（必出）
  - :maxSpawnLimit   可选，默认不设上限

署名：三方同志｜作者交流 QQ 群：528400691
"""
import sys
import re
import argparse
import shutil
from itertools import product


def parse_units(spec):
    """解析 'name*cnt@chance:limit,...' → [(name, cnt, chance, limit)]"""
    out = []
    for item in spec.split(','):
        item = item.strip()
        if not item:
            continue
        limit = None
        if ':' in item:
            item, lim = item.rsplit(':', 1)
            limit = int(lim)
        chance = 1.0
        if '@' in item:
            item, ch = item.rsplit('@', 1)
            chance = float(ch)
        cnt = 1
        if '*' in item:
            item, c = item.rsplit('*', 1)
            cnt = int(c)
        out.append((item.strip(), cnt, chance, limit))
    return out


def build_attr(units):
    """还原成 spawnUnits 属性值字符串。"""
    parts = []
    for name, cnt, chance, limit in units:
        attrs = []
        if chance != 1.0:
            attrs.append('spawnChance=%s' % chance)
        if limit is not None:
            attrs.append('maxSpawnLimit=%d' % limit)
        a = ('(%s)' % ','.join(attrs)) if attrs else ''
        parts.append('%s*%d%s' % (name, cnt, a))
    return ','.join(parts)


def sim_distribution(units):
    """
    模拟所有可能的生成组合（按顺序逐个撑骰 + maxSpawnLimit 卡上限）。
    返回 [(组合元组, 概率)]。
    """
    results = {}
    # 用递归枚举每个单位"出/不出"两种分支
    def rec(i, spawned, prob):
        if prob == 0:
            return
        if i == len(units):
            key = tuple(sorted(spawned))
            results[key] = results.get(key, 0.0) + prob
            return
        name, cnt, chance, limit = units[i]
        total_now = sum(c for _, c in spawned)
        # 分支1：成功生成（若未超上限）
        if limit is None or total_now + cnt <= limit:
            rec(i + 1, spawned + [(name, cnt)], prob * chance)
        # 分支2：失败（或超上限被跳过）
        rec(i + 1, spawned, prob * (1 - chance))
    rec(0, [], 1.0)
    return results


def main():
    ap = argparse.ArgumentParser(description='spawnChance 概率刷兵注入器/模拟器')
    ap.add_argument('tmx', nargs='?', help='地图路径（只算概率可不传）')
    ap.add_argument('--units', required=True, help='单位配方')
    ap.add_argument('--name', default='reward_random_combo')
    ap.add_argument('--x', type=int, default=1300)
    ap.add_argument('--y', type=int, default=1240)
    ap.add_argument('--team', type=int, default=1)
    ap.add_argument('--delay', default='5s')
    ap.add_argument('--activated-by', default='')
    ap.add_argument('--id', type=int, default=2100)
    ap.add_argument('--out', default=None, help='输出路径；不传则原地注入')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    units = parse_units(args.units)

    # ---- 概率分布 ----
    print('=' * 60)
    print('spawnUnits = "%s"' % build_attr(units))
    print('=' * 60)
    print('\n[概率分布（顺序衰减抽签）]')
    dist = sim_distribution(units)
    for combo, p in sorted(dist.items(), key=lambda kv: -kv[1]):
        label = ' + '.join('%s*%d' % (n, c) for n, c in combo) or '(无单位)'
        print('  %6.2f%%   %s' % (p * 100, label))
    print('  ------')
    print('  合计 %.2f%%' % (sum(dist.values()) * 100))

    # 每个单位单独出场率
    print('\n[各单位真实出场率]')
    for name, cnt, chance, limit in units:
        p = 0.0
        for combo, prob in dist.items():
            if any(n == name for n, _ in combo):
                p += prob
        print('  %-22s spawnChance=%-5s → 实际 %5.1f%%' % (name, chance, p * 100))

    if not args.tmx:
        return 0

    # ---- 注入 ----
    with open(args.tmx, encoding='utf-8', errors='surrogateescape') as f:
        raw = f.read()
    ans = raw.rfind('</objectgroup>')
    if ans < 0:
        print('\n[FAIL] 找不到 </objectgroup>')
        return 1

    ab = ('\n      <property name="activatedBy" value="%s"/>' % args.activated_by
          ) if args.activated_by else ''
    obj = (
        '  <object id="%d" name="%s" type="unitAdd" '
        'x="%d" y="%d" width="20" height="20">\n'
        '    <properties>\n'
        '      <property name="spawnUnits" value="%s"/>\n'
        '      <property name="team" value="%d"/>\n'
        '      <property name="delay" value="%s"/>%s\n'
        '    </properties>\n'
        '  </object>\n' % (args.id, args.name, args.x, args.y,
                          build_attr(units), args.team, args.delay, ab))

    new = raw[:ans] + obj + raw[ans:]
    m = re.search(r'nextobjectid="(\d+)"', new)
    if m:
        nid = max(int(m.group(1)), args.id + 1)
        new = re.sub(r'nextobjectid="\d+"', 'nextobjectid="%d"' % nid, new)

    if args.dry_run:
        print('\n[DRY-RUN] 将注入：\n' + obj)
        return 0

    print('\n[注入对象]\n' + obj)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 已写入 %s（%d 字节）' % (args.out, len(new.encode('utf-8'))))
    else:
        shutil.copy(args.tmx, args.tmx + '.bak')
        with open(args.tmx, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(new)
        print('[OK] 原地注入 %s（.bak 已备份）' % args.tmx)
    return 0


if __name__ == '__main__':
    sys.exit(main())