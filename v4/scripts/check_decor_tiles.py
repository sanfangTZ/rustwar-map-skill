#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""装饰瓦片体检（V4.1）：逐格扫描 地面层整合.png 的 alpha，自动区分
「透明底花草树道具」与「满格不透明硬贴片」，并可校验一张 TMX 的
Decorations/Items 层是否只用了安全道具。

用法：
  python3 scripts/check_decor_tiles.py                 # 打印白/黑名单
  python3 scripts/check_decor_tiles.py map.tmx         # 校验某张图
退出码：0=通过，1=发现违规（可直接接 CI/自查流程）。
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np
from PIL import Image

import gen_5v5_common as G

TILE = 20
COLS = 36


def tile_alpha(idx):
    a = np.asarray(Image.open(os.path.join(HERE, "地面层整合.png")).convert("RGBA"))
    r, c = idx // COLS, idx % COLS
    return a[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE, 3].astype(int)


def classify(idx):
    """SAFE(白名单透明道具) / OPAQUE-PATCH(满格硬贴片) / EMPTY / OUT-OF-RANGE / OTHER"""
    if idx >= 1080:
        return "OUT-OF-RANGE"          # 超出 tsx tilecount
    if idx in (G.DECOR_SAFE | G.DECOR_SNOW):
        return "SAFE"
    al = tile_alpha(idx)
    op = int((al > 128).sum())
    corners = [al[0, 0], al[0, -1], al[-1, 0], al[-1, -1]]
    if op <= 5:
        return "EMPTY"
    if op >= 380 and min(corners) > 128:
        return "OPAQUE-PATCH"
    return "OTHER"


def main():
    tmx = sys.argv[1] if len(sys.argv) > 1 else None
    if tmx is None:
        safe = sorted(G.DECOR_SAFE | G.DECOR_SNOW)
        print("== 透明底安全道具 ==")
        for i in safe:
            print(f"  {i:4d}  {classify(i):13s} op={int((tile_alpha(i)>128).sum()):3d}/400")
        print("== 黑名单（硬贴片/图标/空格/超范围）==")
        for i in sorted(G.DECOR_BANNED):
            print(f"  {i:4d}  {classify(i)}")
        return
    root = ET.parse(tmx).getroot()
    import base64, gzip, struct
    W = int(root.get("width")); H = int(root.get("height"))
    fgmap = {ts.get("name"): int(ts.get("firstgid"))
             for ts in root.findall("tileset") if ts.get("firstgid")}
    fg = fgmap.get("地面层整合", 1)
    # Items 层用的是 misc 图集（res_pool 资源块），firstgid = G.MISC_FG
    misc_fg = G.MISC_FG
    bad = []
    for layer in root.findall("layer"):
        name = layer.get("name")
        if name not in ("Decorations", "Items"):
            continue
        d = layer.find("data")
        raw = gzip.decompress(base64.b64decode(d.text))
        gids = struct.unpack("<%dI" % (W * H), raw)
        for pos, g in enumerate(gids):
            if not g:
                continue
            if name == "Items":
                # misc 图集 res_pool（tile id 4）；其余一律违规
                if g != misc_fg + 4:
                    bad.append((name, pos % W, pos // W, g - misc_fg, "NOT-RES_POOL"))
                continue
            tid = g - fg
            cls = classify(tid)
            if cls != "SAFE":
                bad.append((name, pos % W, pos // W, tid, cls))
    if bad:
        print(f"✗ {tmx} 装饰层发现 {len(bad)} 个违规瓦片：")
        for ln, x, y, tid, cls in bad[:40]:
            print(f"  {ln} ({x},{y}) tile={tid} -> {cls}")
        sys.exit(1)
    print(f"✓ {tmx} 装饰层全部使用透明底安全道具")


if __name__ == "__main__":
    main()
