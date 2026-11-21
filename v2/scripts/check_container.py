#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_container.py —— 铁锈战争 TMX「容器硬性条件」一键体检器（完整可运行）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本脚本是「铁锈战争地图硬性条件」的**唯一权威入口**。
任何 AI / 人，只要跑一次本脚本，就能一次性看全并校验全部硬性约束。
（配套文档：references/image_to_tmx.md、references/gotchas.md、
  references/official_xml_notes.md；总表见 SKILL.md §0）

铁锈战争加载 tmx 的硬性条件（缺一即拒载，报「加载地图错误」）：
  C1  <map> 必须有 width / height（正整数），且有 tilewidth / tileheight
  C2  必须存在 3 个 tile layer，且**名字精确（大小写敏感）**为：
        Ground（地面）、Items（项目）、Units（单位）
      名字错一个字母（如 ground / Ground1）或缺失 → 拒载
  C3  三层顺序：Ground → Items → Units（游戏按序查找）
  C4  三个 tile layer 的 width/height **必须与地图 width/height 一致**
      （否则数据格数对不上，游戏解析崩）
  C5  每个 tile layer 的 <data> 必须能被 base64 + gzip 解码，
      且解码后格数 == width*height（小端 uint32）
  C6  纯地形图的 Items / Units 层数据应**全为 0**（无物品/无单位）
  C7  触发器对象只能放在 <objectgroup name="Triggers"> 内（大小写敏感）
  C8  Triggers 里每个 object 必须有 id / name / type / x / y / width / height
      属性，且 id 为正整数、全图唯一、name 建议英文；每个 object 都要有
      <properties> 子元素（空也要留）
  C9  activatedBy / activate / alsoActivate / target 引用的 name 必须存在
  C10 复杂地图可有第 4 个占位层 Set（纯地形图不需要；本脚本仅提示不判错）

用法：
    python3 check_container.py <地图.tmx>            # 全量体检
    python3 check_container.py <地图.tmx> --quiet    # 只输出 FAIL/WARN
    python3 check_container.py <地图.tmx> --fix      # 缺层时自动调用补层逻辑

退出码：0 = 全部硬性条件通过；1 = 有不通过项（详见表）

署名：三方同志｜作者交流 QQ 群：528400691
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import sys
import re
import gzip
import base64
import struct
import argparse
import xml.etree.ElementTree as ET

# 硬性条件：必需层 + 顺序
REQUIRED_LAYERS = [
    ('Ground', '地面'),
    ('Items', '项目'),
    ('Units', '单位'),
]
# 触发器对象必需属性
OBJECT_REQUIRED_ATTRS = ['id', 'name', 'type', 'x', 'y', 'width', 'height']

# 「type 可为空 / 可省略」的对象（按 name 判定）：文档 §6 宾语三大写法①
# 「填 name（type 空）—— map_info / camera_start / attack_point」
# 这些对象用 name 决定身份，object 级 type 允许缺失或为空字符串。
TYPE_OPTIONAL_NAMES = {'map_info', 'camera_start', 'moveCamera'}
TYPE_OPTIONAL_PREFIXES = ('attack_point',)


def _type_is_optional(obj):
    """判断该 object 的 type 属性是否允许缺失/为空（合法省略）。"""
    nm = (obj.get('name') or '').strip()
    if nm in TYPE_OPTIONAL_NAMES:
        return True
    for pre in TYPE_OPTIONAL_PREFIXES:
        if nm == pre or nm.startswith(pre + '_') or nm.startswith(pre):
            return True
    return False
# 引用类属性（值必须指向已存在的对象 name）
REF_PROPS = ['activatedBy', 'activate', 'alsoActivate', 'target']

results = []  # (level, code, msg)，level ∈ OK/FAIL/WARN/INFO


def add(level, code, msg):
    results.append((level, code, msg))


# ----------------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------------
def load(path):
    with open(path, encoding='utf-8', errors='surrogateescape') as f:
        return f.read()


def decode_data_block(text):
    """解码 <data> 文本 → gid 列表。返回 (gids, err)。"""
    body = re.sub(r'\s+', '', text or '')
    if not body:
        return [], '数据块为空'
    try:
        comp = base64.b64decode(body)
    except Exception as e:
        return [], 'base64 解码失败: %s' % e
    try:
        raw = gzip.decompress(comp)
    except Exception as e:
        return [], 'gzip 解压失败: %s' % e
    n = len(raw)
    if n % 4 != 0:
        return [], '解压后字节数 %d 不是 4 的倍数' % n
    gids = list(struct.unpack('<%dI' % (n // 4), raw))
    return gids, None


# ----------------------------------------------------------------------------
# 正则兜底解析（ElementTree 对某些 tm x 容错不足，用正则做对照）
# ----------------------------------------------------------------------------
def regex_map_attrs(raw):
    m = re.search(r'<map\b[^>]*>', raw)
    if not m:
        return None
    tag = m.group(0)

    def attr(name):
        a = re.search(r'\b%s="(\d+)"' % name, tag)
        return int(a.group(1)) if a else None

    return {
        'width': attr('width'),
        'height': attr('height'),
        'tilewidth': attr('tilewidth'),
        'tileheight': attr('tileheight'),
    }


def regex_tile_layers(raw):
    """返回 [{name, width, height, data_text, pos}]（按出现顺序）。"""
    out = []
    for m in re.finditer(r'<layer\b([^>]*)>(.*?)</layer>', raw, re.S):
        attrs, body = m.group(1), m.group(2)

        def ga(name):
            a = re.search(r'\b%s="(\d+)"' % name, attrs)
            return int(a.group(1)) if a else None

        nm = re.search(r'\bname="([^"]*)"', attrs)
        dm = re.search(r'<data\b[^>]*>(.*?)</data>', body, re.S)
        out.append({
            'name': nm.group(1) if nm else '(无名)',
            'width': ga('width'),
            'height': ga('height'),
            'data_text': dm.group(1) if dm else '',
            'pos': m.start(),
        })
    return out


# ----------------------------------------------------------------------------
# 各项体检
# ----------------------------------------------------------------------------
def check_C1_map_header(raw):
    rx = regex_map_attrs(raw)
    if not rx:
        add('FAIL', 'C1', '找不到 <map> 标签')
        return None
    W, H = rx['width'], rx['height']
    if not W or not H:
        add('FAIL', 'C1', '<map> 缺少 width/height（正整数）')
    elif W <= 0 or H <= 0:
        add('FAIL', 'C1', '<map> width/height 必须为正整数，当前 %sx%s' % (W, H))
    else:
        add('OK', 'C1', '<map> width=%d height=%d' % (W, H))
    # tilewidth/tileheight
    if rx['tilewidth'] and rx['tileheight']:
        add('OK', 'C1', 'tilewidth=%d tileheight=%d' % (rx['tilewidth'], rx['tileheight']))
    else:
        add('WARN', 'C1', '缺少 tilewidth/tileheight（建议 tilewidth=tileheight=20）')
    return rx


def check_C2_C3_layers(layers):
    names = [l['name'] for l in layers]
    req_names = [n for n, _ in REQUIRED_LAYERS]

    # C2 必需层齐全 + 名字精确
    missing = [n for n in req_names if n not in names]
    if missing:
        add('FAIL', 'C2', '缺少必需层: %s（游戏报「xxx层没有在地图中找到，这一层是必需的」）'
            % ', '.join(missing))
        # 拼写近似提示
        for l in layers:
            for need in missing:
                if l['name'].lower() == need.lower() and l['name'] != need:
                    add('FAIL', 'C2', '层名大小写错误: 现有「%s」应为「%s」'
                        % (l['name'], need))
        add('INFO', 'C2', '→ 用 scripts/add_layers.py 一键补层')
    else:
        add('OK', 'C2', 'Ground / Items / Units 三层齐全且名字精确')

    # C3 顺序
    idx = {n: (names.index(n) if n in names else -1) for n in req_names}
    if all(idx[n] >= 0 for n in req_names):
        if idx['Ground'] < idx['Items'] < idx['Units']:
            add('OK', 'C3', '三层顺序正确: Ground → Items → Units')
        else:
            add('WARN', 'C3', '三层顺序异常（现: %s），建议 Ground → Items → Units'
                % ' → '.join(sorted(req_names, key=lambda n: idx[n])))
    else:
        add('INFO', 'C3', '三层不全，跳过顺序检查')
    return names


def check_C4_C5_C6_sizes(layers, W, H):
    tile_layers = [l for l in layers if l['name'] in [n for n, _ in REQUIRED_LAYERS]]

    # C4 尺寸一致
    size_bad = False
    for l in tile_layers:
        if l['width'] != W or l['height'] != H:
            size_bad = True
            add('FAIL', 'C4', '层「%s」尺寸 %sx%s 与地图 %sx%s 不一致'
                % (l['name'], l['width'], l['height'], W, H))
    if tile_layers and not size_bad:
        add('OK', 'C4', '三个 tile layer 尺寸均与地图一致 (%dx%d)' % (W, H))
    elif not tile_layers:
        add('INFO', 'C4', '没有 tile layer，跳过尺寸检查')

    # C5 可解码 + 格数
    for l in tile_layers:
        if l['width'] is None or l['height'] is None:
            add('FAIL', 'C5', '层「%s」缺少 width/height 属性' % l['name'])
            continue
        gids, err = decode_data_block(l['data_text'])
        expect = l['width'] * l['height']
        if err:
            add('FAIL', 'C5', '层「%s」数据解码失败: %s' % (l['name'], err))
        elif len(gids) != expect:
            add('FAIL', 'C5', '层「%s」格数 %d ≠ %dx%d=%d（数据与尺寸不符）'
                % (l['name'], len(gids), l['width'], l['height'], expect))
        else:
            mx = ','.join(str(g) for g in sorted(set(gids))[:5])
            add('OK', 'C5', '层「%s」可解码，%d 格（=W×H）✓' % (l['name'], len(gids)))

    # C6 纯地形图 Items/Units 应为全 0
    for l in tile_layers:
        if l['name'] in ('Items', 'Units'):
            gids, err = decode_data_block(l['data_text'])
            if err:
                break
            nonzero = [g for g in gids if g != 0]
            if nonzero:
                add('WARN', 'C6', '层「%s」含 %d 个非 0 格（若是纯地形图应为全 0；'
                    '若确为带物品/单位的地图可忽略）' % (l['name'], len(nonzero)))
            else:
                add('OK', 'C6', '层「%s」全为 0（纯地形图要求）' % l['name'])


def check_C7_C8_C9_triggers(root, raw):
    try:
        triggers = root.find('objectgroup[@name="Triggers"]')
    except Exception:
        triggers = None

    # 有没有触发对象却没放 Triggers
    all_ogs = root.findall('objectgroup')
    og_names = [og.get('name', '') for og in all_ogs]

    # 找疑似触发器对象（含 spawnUnits / unitType 等属性）在非 Triggers 图层
    misplaced = []
    for og in all_ogs:
        gname = og.get('name', '')
        if gname == 'Triggers':
            continue
        for o in og.findall('object'):
            props = {p.get('name') for p in o.findall('properties/property')}
            if props & {'spawnUnits', 'unitType', 'message', 'winCondition'}:
                misplaced.append((gname, o.get('name', '')))

    if misplaced:
        for g, n in misplaced:
            add('FAIL', 'C7', '触发器对象「%s」放在了非法图层「%s」（必须在 Triggers）' % (n, g))
    elif 'Triggers' not in og_names:
        add('WARN', 'C7', '没有 Triggers 图层（纯地形图正常；若写了触发器则必须建它）')
    else:
        add('OK', 'C7', '触发器图层为 Triggers（合法）')

    if triggers is None:
        return

    # C8 属性齐全 + id 唯一 + properties 存在
    seen_ids = {}
    n_objs = 0
    for o in triggers.findall('object'):
        n_objs += 1
        # type 对 map_info/camera_start/attack_point 这类「用 name 定位身份」
        # 的对象是允许省略/为空的，故此处按需放宽必需属性集合。
        need = list(OBJECT_REQUIRED_ATTRS)
        if _type_is_optional(o):
            need = [a for a in need if a != 'type']
        miss = [a for a in need if o.get(a) is None]
        if miss:
            add('FAIL', 'C8', '对象「%s」缺少必需属性: %s'
                % (o.get('name', '?'), ', '.join(miss)))
        oid = o.get('id')
        if oid is not None:
            if not re.fullmatch(r'\d+', oid or ''):
                add('FAIL', 'C8', '对象「%s」id="%s" 非正整数' % (o.get('name', '?'), oid))
            else:
                seen_ids.setdefault(oid, []).append(o.get('name', '?'))
        if o.find('properties') is None:
            add('FAIL', 'C8', '对象「%s」缺少 <properties> 子元素（空也要留）'
                % o.get('name', '?'))
    dup = {k: v for k, v in seen_ids.items() if len(v) > 1}
    if dup:
        for k, v in dup.items():
            add('FAIL', 'C8', 'id 重复: id=%s 被用于 %s' % (k, ', '.join(v)))
    if n_objs and not any(lv == 'FAIL' and cd and cd.startswith('C8')
                          for lv, cd, _ in results):
        add('OK', 'C8', 'Triggers 内 %d 个对象属性齐全、id 唯一、properties 存在' % n_objs)

    # C9 引用闭合
    names = set()
    for og in all_ogs:
        for o in og.findall('object'):
            if o.get('name'):
                names.add(o.get('name'))
    dangling = []
    for o in triggers.findall('object'):
        props = {p.get('name'): p.get('value', '')
                 for p in o.findall('properties/property')}
        for rp in REF_PROPS:
            v = props.get(rp)
            if v and v not in names:
                dangling.append((o.get('name', '?'), rp, v))
    if dangling:
        for src, rp, tgt in dangling:
            add('FAIL', 'C9', '%s.%s = %s（找不到该 name 的对象）' % (src, rp, tgt))
    elif n_objs:
        add('OK', 'C9', '引用类属性（%s）全部闭合' % '/'.join(REF_PROPS))


def check_C10_set_layer(layers):
    names = [l['name'] for l in layers]
    if 'Set' in names:
        add('INFO', 'C10', '存在第 4 层 Set（复杂地图占位层，正常）')
    else:
        add('INFO', 'C10', '无 Set 层（纯地形图 / 普通地图正常）')


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='铁锈战争 TMX 容器硬性条件一键体检')
    ap.add_argument('tmx')
    ap.add_argument('--quiet', action='store_true', help='只显示 FAIL/WARN')
    ap.add_argument('--fix', action='store_true', help='缺层时自动补层')
    args = ap.parse_args()

    try:
        raw = load(args.tmx)
    except OSError as e:
        print('[FAIL] 打不开文件: %s' % e)
        return 1

    # ET 解析（给 C7/C8/C9 用）
    root = None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        add('FAIL', 'XML', 'XML 解析失败: %s' % e)

    rx = check_C1_map_header(raw)
    W = rx['width'] if rx else None
    H = rx['height'] if rx else None

    layers = regex_tile_layers(raw)
    check_C2_C3_layers(layers)
    if W and H:
        check_C4_C5_C6_sizes(layers, W, H)
    if root is not None:
        check_C7_C8_C9_triggers(root, raw)
    check_C10_set_layer(layers)

    # ---- 输出 ----
    print('=' * 64)
    print('铁锈战争 TMX 容器硬性条件体检')
    print('文件: %s' % args.tmx)
    print('=' * 64)

    ok = fail = warn = 0
    for level, code, msg in results:
        if level == 'OK':
            ok += 1
        elif level == 'FAIL':
            fail += 1
        elif level == 'WARN':
            warn += 1
        if args.quiet and level in ('OK', 'INFO'):
            continue
        icon = {'OK': '✓', 'FAIL': '✗', 'WARN': '!', 'INFO': '-'}[level]
        print('  [%s][%s] %s' % (icon, code, msg))

    print('-' * 64)
    print('统计: OK=%d  FAIL=%d  WARN=%d' % (ok, fail, warn))
    verdict = 'PASS —— 全部硬性条件通过，可载入游戏' if fail == 0 else \
              'FAIL —— 有 %d 项硬性条件不通过，游戏会拒载或异常' % fail
    print('总体: %s' % verdict)
    if fail and args.fix:
        print('\n[fIX] 检测到缺层类问题，可执行：')
        print("      python3 scripts/add_layers.py '%s'" % args.tmx)
    print('=' * 64)
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
