#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 tmx 地图 Triggers 触发层注入模板脚本

思路:
  1. 先备份(双备份: .bak 带时间)
  2. 读出 Triggers 段最后一个 </object> 的位置
  3. 把新 object 插到它后面、</objectgroup> 前面
  4. 写出到新文件(或就地)

用法:
  python3 insert_triggers.py <tmx路径> <新object片段文件> [--inplace]

新 object 片段建议写成一行或多行 XML,示例:
  <object id="9001" name="锚点A" type="trigger" .../>
"""
import sys
import re
import os
import time
import shutil


def backup(path):
    ts = time.strftime('%Y%m%d_%H%M%S')
    bak = path + '.bak.' + ts
    shutil.copy2(path, bak)
    return bak


def find_insert_point(s):
    """返回 (最后一个 </object> 的结束下标, </objectgroup> 的起始下标)"""
    m = re.search(r'name="Triggers"[^>]*>(.*?)</objectgroup>', s, re.S)
    if not m:
        raise RuntimeError('未找到 Triggers 段')
    seg_start = m.start(1)
    seg = m.group(1)
    # 段内最后一个 </object>
    last = None
    for mm in re.finditer(r'</object\s*>', seg):
        last = mm
    if last is None:
        raise RuntimeError('Triggers 段内没有 </object> 可作锚点')
    insert_at = seg_start + last.end()
    return insert_at


def main():
    if len(sys.argv) < 3:
        print('用法: python3 insert_triggers.py <tmx路径> <片段文件> [--inplace]')
        sys.exit(1)
    path = sys.argv[1]
    frag_path = sys.argv[2]
    inplace = '--inplace' in sys.argv[3:]

    with open(path, 'r', encoding='utf-8') as f:
        s = f.read()
    with open(frag_path, 'r', encoding='utf-8') as f:
        frag = f.read().strip()

    # 1. 备份
    bak = backup(path)
    print('[备份]', bak)

    # 2. 定位
    at = find_insert_point(s)
    print('[插入点] 字符偏移', at)

    # 3. 插入(前后加换行, 保持格式)
    new = s[:at] + '\n' + frag + '\n' + s[at:]

    # 4. 写回
    out = path if inplace else (path + '.new')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(new)
    print('[写出]', out, len(new), '字符')

    # 5. 快速自检
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(new)
        print('[自检] XML_PARSE_OK')
    except Exception as e:
        print('[自检] XML_PARSE_FAIL:', e)
        print('  ==> 注入后 XML 不合法! 保留备份, 请回滚')

    if not inplace and os.path.exists(out):
        print('提示: 未加 --inplace, 新文件为', out)


if __name__ == '__main__':
    main()
