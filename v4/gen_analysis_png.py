#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地形解析图：类别配色 + 出生点 + 矿点 + 中轴 + 图例（一眼看清结构/对称/资源分布）"""
import os, sys
from rwmap import Map
from PIL import Image, ImageDraw, ImageFont
import xml.etree.ElementTree as ET
from collections import Counter

# terrain 众数类别 → 颜色 / 名称
CAT_COLOR = {
    0: (96, 180, 96),     # 草地
    1: (190, 155, 95),    # 土
    2: (150, 150, 158),   # 石
    3: (226, 210, 150),   # 沙
    4: (126, 96, 60),     # 泥
    5: (240, 240, 245),   # 雪
    6: (150, 210, 220),   # 浅水
    7: (70, 130, 225),    # 水
    8: (40, 90, 185),     # 海
    9: (20, 55, 140),     # 洋
    11: (235, 90, 40),    # 岩浆
    12: (50, 130, 70),    # 高草
    14: (95, 95, 105),    # 高石
    23: (120, 190, 230),  # 浅滩
    26: (90, 150, 90),    # 短草
}
CAT_NAME = {0: "草地", 1: "土", 2: "石", 3: "沙", 4: "泥", 5: "雪", 6: "浅水",
            7: "水", 8: "海", 9: "洋", 11: "岩浆", 12: "高草", 14: "高石",
            23: "浅滩", 26: "短草"}

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

def get_items_layer(tmx):
    root = ET.parse(tmx).getroot()
    for l in root.findall("layer"):
        if l.get("name") == "Items":
            return l

def get_spawns(tmx):
    root = ET.parse(tmx).getroot()
    out = []
    for g in root.findall("objectgroup"):
        if g.get("name") == "UnitObjects":
            for o in g.findall("object"):
                props = {p.get("name"): p.get("value") for p in (o.find("properties").findall("property") if o.find("properties") is not None else [])}
                if props.get("unit") == "commandCenter":
                    out.append((int(float(o.get("x"))) // 20, int(float(o.get("y"))) // 20, props.get("team", "?")))
    return out

def render(tmx, out_png, scale=4):
    m = Map(tmx)
    g = m.cat_grid()
    H, W = len(g), len(g[0])
    used = Counter(v for row in g for v in row)
    legend_n = len([k for k in used if k in CAT_COLOR])
    panel_w = 150
    img_w = W * scale + panel_w
    img_h = max(H * scale, legend_n * 26 + 40)
    im = Image.new("RGB", (img_w, img_h), (20, 20, 24))
    d = ImageDraw.Draw(im)
    # 地形块
    for r in range(H):
        for c in range(W):
            col = CAT_COLOR.get(g[r][c], (255, 0, 255))
            d.rectangle([c * scale, r * scale, (c + 1) * scale - 1, (r + 1) * scale - 1], fill=col)
    # 中轴
    ax = int(99.5 * scale)
    for y in range(0, H * scale, 8):
        d.line([(ax, y), (ax, min(y + 4, H * scale))], fill=(255, 255, 255), width=1)
    # 出生点
    try:
        f = ImageFont.truetype(FONT_PATH, 15, index=0)
    except Exception:
        f = ImageFont.load_default()
    for (c, r, team) in get_spawns(tmx):
        col = (235, 70, 70) if c < 100 else (70, 130, 235)
        x, y = c * scale, r * scale
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=col, width=2)
        d.text((x + 8, y - 8), str(team), font=f, fill=(255, 255, 255))
    # 矿点
    items = m.layers.get("Items")
    # 矿坑中心 GID = 图集末段 + 4（misc tile4=res_pool）；3×3 边框其余 8 格不重复标框
    center_gid = None
    for ts in m.tilesets:
        center_gid = ts.firstgid + ts.tilecount - 18 + 4   # misc 18 格里的 tile4
    if items:
        for r in range(H):
            for c in range(W):
                if items[r * W + c] and (center_gid is None or items[r * W + c] == center_gid):
                    x, y = c * scale, r * scale
                    # 矿坑 = 3×3 框（中心矿 + 四周边框）
                    d.rectangle([x - scale, y - scale, x + 2 * scale, y + 2 * scale], outline=(255, 210, 0), width=2)
    # 图例
    lx = W * scale + 12
    ly = 20
    try:
        f2 = ImageFont.truetype(FONT_PATH, 16, index=0)
    except Exception:
        f2 = ImageFont.load_default()
    for k in sorted(used, key=lambda x: (x not in CAT_COLOR, x)):
        if k not in CAT_COLOR:
            continue
        d.rectangle([lx, ly, lx + 16, ly + 16], fill=CAT_COLOR[k], outline=(80, 80, 80))
        d.text((lx + 22, ly - 2), CAT_NAME.get(k, str(k)), font=f2, fill=(235, 235, 235))
        ly += 26
    d.text((lx, ly + 8), "● 红/蓝圈=出生点\n■ 黄点=矿\n| 白虚线=中轴", font=f2, fill=(220, 220, 220))
    im.save(out_png)
    print(f"  {os.path.basename(out_png)}: {W}x{H} 图例类别 {legend_n}")

if __name__ == "__main__":
    src = "/workspace/重做地图/纯地形版"
    outdir = os.path.join(src, "地形解析")
    os.makedirs(outdir, exist_ok=True)
    for fn in sorted(os.listdir(src)):
        if fn.endswith(".tmx"):
            render(os.path.join(src, fn), os.path.join(outdir, fn.replace(".tmx", "_地形解析.png")))
    print("完成 →", outdir)
