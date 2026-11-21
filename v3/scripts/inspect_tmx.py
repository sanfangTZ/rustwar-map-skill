#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspect_tmx.py —— 铁锈战争 TMX 地图侦察器（完整可运行）

用途：在改图/注入触发之前，先“侦察”一份 tmx 的结构：
  1. 列出所有层（Ground / Items / Units / Set / Triggers / ObjectUnits ...）
  2. 列出 Triggers 里所有 object（id / name / type / x / y）
  3. 导出 ObjectUnits / Units 层里的单位清单
  4. 体检：缺必需层？负坐标？悬空 activatedBy 引用？

用法：
    python3 inspect_tmx.py <地图.tmx>            # 完整侦察
    python3 inspect_tmx.py <地图.tmx> --triggers  # 只看 Triggers 对象
    python3 inspect_tmx.py <地图.tmx> --units     # 只看单位

退出码：0 = 结构健康；1 = 发现缺失层/异常

署名：三方同志｜作者交流 QQ 群：528400691
"""
import sys
import re
import xml.etree.ElementTree as ET


def load(path):
    with open(path, encoding='utf-8', errors='surrogateescape') as f:
        return f.read()


def list_layers(root):
    layers = []
    for child in root:
        tag = child.tag
        name = child.get('name', '(无名)')
        w = child.get('width', '-')
        h = child.get('height', '-')
        layers.append((tag, name, w, h))
    return layers


def list_objects(root):
    objs = []
    for og in root.findall('objectgroup'):
        gname = og.get('name', '')
        for o in og.findall('object'):
            props = {}
            for p in o.findall('properties/property'):
                props[p.get('name')] = p.get('value', '')
            objs.append({
                'group': gname,
                'id': o.get('id'),
                'name': o.get('name', ''),
                'type': o.get('type', ''),
                'x': o.get('x'), 'y': o.get('y'),
                'w': o.get('width'), 'h': o.get('height'),
                'props': props,
            })
    return objs


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else '--all'

    try:
        raw = load(path)
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print('[FAIL] XML 解析失败: %s' % e)
        return 1

    print('=' * 60)
    print('文件: %s' % path)
    print('字符数: %d' % len(raw))
    print('=' * 60)

    # ---- 层 ----
    print('\n[层清单]')
    layers = list_layers(root)
    for tag, name, w, h in layers:
        print('  %-14s %-16s %sx%s' % (tag, name, w, h))

    layer_names = [n for _, n, _, _ in layers]
    needed = ['Ground', 'Items', 'Units']
    missing = [n for n in needed if n not in layer_names]
    print('\n[必需层体检]')
    if missing:
        print('  [FAIL] 缺少必需层: %s' % ', '.join(missing))
        print('         → 游戏会报“加载地图错误：xxx层没有在地图中找到”')
        print('         → 用 scripts/add_layers.py 补层')
    else:
        print('  [OK] Ground / Items / Units 三层齐全')

    # ---- 对象 ----
    objs = list_objects(root)
    if mode in ('--all', '--triggers'):
        print('\n[Triggers / 对象清单]  共 %d 个' % len(objs))
        for o in objs:
            tn = o['type']
            if tn == 'unitAdd':
                extra = o['props'].get('spawnUnits', '')
                ab = o['props'].get('activatedBy', '')
                print('  #%-4s %-22s %-10s x=%-5s y=%-5s spawn=%s%s'
                      % (o['id'], o['name'], tn, o['x'], o['y'], extra,
                         (' activatedBy=%s' % ab) if ab else ''))
            else:
                print('  #%-4s %-22s %-10s x=%-5s y=%-5s'
                      % (o['id'], o['name'], tn, o['x'], o['y']))

    # ---- 单位导出 ----
    if mode in ('--all', '--units'):
        print('\n[Units 层单位导出]')
        # 从 ObjectUnits objectgroup 或 Units 层属性里找
        found = False
        for og in root.findall('objectgroup'):
            if og.get('name') in ('ObjectUnits', 'units'):
                for o in og.findall('object'):
                    found = True
                    print('  %s (%s) team=%s unit=%s' % (
                        o.get('name', ''), o.get('type', ''),
                        (o.find('properties/property[@name="team"]') or {}).get('value', ''),
                        (o.find('properties/property[@name="unit"]') or {}).get('value', '')))
        if not found:
            print('  (未找到 ObjectUnits 单位对象)')

    # ---- 引用体检 ----
    print('\n[引用体检]')
    names = set(o['name'] for o in objs if o['name'])
    dangling = []
    for o in objs:
        ab = o['props'].get('activatedBy')
        if ab and ab not in names:
            dangling.append((o['name'], ab))
    if dangling:
        for src, tgt in dangling:
            print('  [FAIL] %s.activatedBy = %s （找不到目标对象）' % (src, tgt))
    else:
        print('  [OK] activatedBy 引用全部闭合')

    bad_coord = re.findall(r'[xy]="-\d+"', raw)
    if bad_coord:
        print('  [WARN] 发现负坐标 %d 处（可能被引擎 clamp）' % len(bad_coord))
    else:
        print('  [OK] 无负坐标')

    print('\n' + '=' * 60)
    ok = not missing and not dangling
    print('总体: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
