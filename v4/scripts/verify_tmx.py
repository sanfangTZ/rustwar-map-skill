#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 tmx 地图 Triggers 触发层一键校验脚本

用法:
    python3 verify_tmx.py <tmx路径> [要检查的name1 name2 ...]

会输出:
  1. XML 是否合法
  2. Triggers 段对象数量
  3. 指定 name 是否存在(可多个)
  4. 悬空引用检查(objects 的 activatedBy/activate 指向不存在的 name)
  5. 常见错别字/繁体抽样检查(简单版)
"""
import sys
import re
import xml.etree.ElementTree as ET


def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def check_xml(s):
    try:
        ET.fromstring(s)
        return True, 'XML_PARSE_OK'
    except Exception as e:
        return False, 'XML_PARSE_FAIL: %s' % e


def get_triggers_segment(s):
    """取出 name=\"Triggers\" 的 objectgroup 内容"""
    m = re.search(r'name="Triggers"[^>]*>(.*?)</objectgroup>', s, re.S)
    if not m:
        return None
    return m.group(1)


def count_objects(seg):
    return len(re.findall(r'<object[ >]', seg))


def all_names(seg):
    return re.findall(r'<object[^>]*\bname="([^"]*)"', seg)


def check_targets(seg, targets):
    names = set(all_names(seg))
    ok, miss = [], []
    for t in targets:
        (ok if t in names else miss).append(t)
    return ok, miss


def check_dangling(s):
    """全图扫描: activate/activatedBy/alsoActivate 引用的 name 是否存在"""
    # 定义对象 name
    defined = set(re.findall(r'<object[^>]*\bname="([^"]*)"', s))
    dangling = []
    for attr in ('activate', 'activatedBy', 'alsoActivate'):
        for m in re.finditer(attr + r'="([^"]*)"', s):
            for ref in m.group(1).split(','):
                ref = ref.strip()
                if ref and ref not in defined:
                    dangling.append((attr, ref))
    return dangling


# 常见错别字 / 繁体抽样(可按项目补充)
TYPO = {
    '結晶': '结晶', '清剿': '清剿', '疑云': '疑云',
    '防卫': '防御', '虫族': '虫族',
}


def check_typo(s):
    hits = []
    if re.search(r'[\u4e00-\u9fff]', s):
        # 繁体常用字抽查
        trad = ['這', '個', '說', '對', '們', '時', '實', '為', '結', '雲']
        for ch in trad:
            if ch in s:
                hits.append(ch)
    for bad, good in TYPO.items():
        if bad in s and bad != good:
            hits.append('%s->%s' % (bad, good))
    return hits


def main():
    if len(sys.argv) < 2:
        print('用法: python3 verify_tmx.py <tmx路径> [name1 name2 ...]')
        sys.exit(1)
    path = sys.argv[1]
    targets = sys.argv[2:]

    s = load(path)
    print('文件:', path)
    print('字符数:', len(s))

    xml_ok, xml_msg = check_xml(s)
    print('[1] XML:', xml_msg)

    seg = get_triggers_segment(s)
    if seg is None:
        print('[2] Triggers 段: 未找到!')
    else:
        n = count_objects(seg)
        print('[2] Triggers 对象数:', n)
        if targets:
            ok, miss = check_targets(seg, targets)
            for t in ok:
                print('    FOUND  :', t)
            for t in miss:
                print('    MISSING:', t)

    dangling = check_dangling(s)
    if dangling:
        print('[3] 悬空引用(需人工确认是否原有问题):')
        for attr, ref in dangling:
            print('    %s -> %s' % (attr, ref))
    else:
        print('[3] 悬空引用: 无')

    typos = check_typo(s)
    if typos:
        print('[4] 疑似繁体/错别字:', ', '.join(typos))
    else:
        print('[4] 疑似繁体/错别字: 无')

    if xml_ok and not [t for t in targets if t not in set(all_names(seg or ''))]:
        print('\n==> 总体: PASS')
    else:
        print('\n==> 总体: 需人工复核')


if __name__ == '__main__':
    main()
