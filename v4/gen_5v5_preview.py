#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立解码校验 + 渲染带标注预览（不采信生成器自报，直接解析写出的 .tmx）"""
import os, base64, gzip, struct, math
import numpy as np
import xml.etree.ElementTree as ET
from collections import Counter, deque
import gen_combined as C
import gen_koth as K
import gen_5v5_common as G
from PIL import Image, ImageDraw, ImageFont

SIZE = G.SIZE
IMPASS = G.IMPASS
NM = G.NM


def decode_layers(tmx):
    root = ET.parse(tmx).getroot()
    out = {}
    for l in root.findall("layer"):
        raw = base64.b64decode(l.find("data").text.strip())
        buf = gzip.decompress(raw)
        g = struct.unpack("<%dI" % (len(buf) // 4), buf)
        out[l.get("name")] = [list(g[i * SIZE:(i + 1) * SIZE]) for i in range(SIZE)]
    return root, out


def decode_grid(out):
    """从 Ground 层反推地形角索引（tid-1 → 查 tsx terrain）。"""
    root, _ = None, None
    ground = out["Ground"]
    # 读 tsx terrain 属性
    tsx = C.TSX
    import xml.etree.ElementTree as ET
    r = ET.parse(tsx).getroot()
    tid2corners = {}
    for t in r.findall("tile"):
        tid = int(t.get("id")); terr = t.get("terrain")
        tid2corners[tid] = tuple(int(x) for x in terr.split(",")) if terr else None
    grid = [[0] * SIZE for _ in range(SIZE)]
    for rr in range(SIZE):
        for cc in range(SIZE):
            gid = ground[rr][cc]
            tid = gid - G.GROUND_FG
            corners = tid2corners.get(tid)
            if corners:
                grid[rr][cc] = corners[0]   # 取 NW 角作为该格主导地形
    return grid


def get_units(tmx):
    root = ET.parse(tmx).getroot()
    uo = root.find("objectgroup[@name='UnitObjects']")
    spawns, crystals = [], []
    for o in uo.findall("object"):
        p = o.find("properties")
        d = {pr.get("name"): pr.get("value") for pr in p.findall("property")} if p is not None else {}
        unit = d.get("unit"); team = d.get("team")
        x = int(o.get("x", 0)) // 20; y = int(o.get("y", 0)) // 20
        if unit == "commandCenter":
            spawns.append((y, x, int(team)))
        elif unit == "crystalResource":
            crystals.append((y, x))
    return spawns, crystals


def bfs(grid, sr, sc):
    dist = [[-1] * SIZE for _ in range(SIZE)]
    if grid[sr][sc] in IMPASS:
        return dist
    q = deque([(sr, sc)]); dist[sr][sc] = 0
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < SIZE and 0 <= cc < SIZE and dist[rr][cc] < 0 and grid[rr][cc] not in IMPASS:
                dist[rr][cc] = dist[r][c] + 1; q.append((rr, cc))
    return dist


def verify(grid, spawns, crystals, bands):
    sp = [(s[0], s[1]) for s in spawns]
    base = bfs(grid, sp[0][0], sp[0][1])
    reachable = all(base[r][c] >= 0 for (r, c) in sp)
    pair_ok = True
    for i in range(len(sp)):
        d = bfs(grid, sp[i][0], sp[i][1])
        for j in range(len(sp)):
            if d[sp[j][0]][sp[j][1]] < 0:
                pair_ok = False
    cd = bfs(grid, 100, 100)
    left = [cd[r][c] for (r, c, t) in spawns if t % 2 == 0]
    right = [cd[r][c] for (r, c, t) in spawns if t % 2 == 1]
    bal = abs(sum(left)/len(left) - sum(right)/len(right)) / max(max(left), max(right)) * 100
    n_pass = 0
    for (r0, r1, c0, c1) in bands:
        g2 = [row[:] for row in grid]
        for rr in range(r0, min(r1, SIZE - 1) + 1):
            for cc in range(c0, min(c1, SIZE - 1) + 1):
                g2[rr][cc] = G.HIGHSTONE
        sd = bfs(g2, sp[0][0], sp[0][1])
        if any(sd[r][c] >= 0 for (r, c, t) in spawns if t % 2 == 1):
            n_pass += 1
    return reachable, pair_ok, bal, n_pass


def render_annotated(tmx, out_png, title, bands, extra_rects=None):
    K.render(tmx, out_png)
    im = Image.open(out_png).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    TILE = 20
    spawns, crystals = get_units(tmx)
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        f_big = ImageFont.truetype(FONT, 30, index=0)
        f_mid = ImageFont.truetype(FONT, 22, index=0)
    except Exception:
        f_big = f_mid = ImageFont.load_default()
    LEFT = (225, 45, 45); RIGHT = (40, 130, 235); AXIS = (255, 200, 0); CRYST = (0, 200, 220)
    for (sr, sc, team) in spawns:
        cx, cy = sc * TILE, sr * TILE
        col = LEFT if team % 2 == 0 else RIGHT
        d.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], outline=col, width=5)
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=col)
        d.text((cx, cy), f"T{team}", font=f_mid, fill=(255, 255, 255), anchor="mm")
    for (rr, cc) in crystals:
        cx, cy = cc * TILE, rr * TILE
        d.rectangle([cx - 7, cy - 7, cx + 7, cy + 7], fill=CRYST, outline=(255, 255, 255))
    for (r0, r1, c0, c1) in bands:
        d.rectangle([c0 * TILE, r0 * TILE, (c1 + 1) * TILE, (r1 + 1) * TILE], outline=AXIS, width=3)
    if extra_rects:
        for (r0, r1, c0, c1, col) in extra_rects:
            d.rectangle([c0 * TILE, r0 * TILE, (c1 + 1) * TILE, (r1 + 1) * TILE], outline=col, width=3)
    lx, ly, lw, lh = 24, 24, 880, 150
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    d.ellipse([lx + 18, ly + 18, lx + 58, ly + 58], outline=LEFT, width=5)
    d.text((lx + 72, ly + 34), "左 偶数队 0/2/4/6/8", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 18, ly + 74, lx + 58, ly + 114], outline=RIGHT, width=5)
    d.text((lx + 72, ly + 90), "右 奇数队 1/3/5/7/9", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.line([(lx + 470, ly + 46), (lx + 506, ly + 46)], fill=AXIS, width=5)
    d.text((lx + 516, ly + 46), "地面通道(黄框)", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.rectangle([lx + 470, ly + 80, lx + 506, ly + 116], fill=CRYST, outline=(255, 255, 255))
    d.text((lx + 516, ly + 90), "中立水晶", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.text((lx + 700, ly + 34), title, font=f_big, fill=(255, 220, 0), anchor="lm")
    im.save(out_png)
    return im


def check(name, tmx, bands, extra=None):
    root, out = decode_layers(tmx)
    grid = decode_grid(out)
    spawns, crystals = get_units(tmx)
    reach, pair, bal, npass = verify(grid, spawns, crystals, bands)
    terr = Counter()
    for row in grid:
        for v in row:
            terr[v] += 1
    total = SIZE * SIZE
    gcc = G.largest_grass_cc(grid)
    open_share = G.central_open_share(grid)
    ctr = G.central_max_terrain(grid)
    print(f"\n[{name}] 独立解码校验")
    print(f"  地形类别={len(terr)} 最大占比={max(terr.values())/total*100:.1f}% "
          f"草地连片={100*gcc/total:.1f}% 中央开阔={open_share:.1f}%(峰值{ctr:.1f}%)")
    print(f"  连通10点={reach} 两两={pair} 通道={npass} 平衡差={bal:.1f}% 水晶={len(crystals)}")
    print(f"  地形top: {{{', '.join(f'{NM.get(k,k)}:{v/total*100:.1f}%' for k,v in terr.most_common(6))}}}")
    return reach and pair and npass >= 3 and bal < 15 and len(terr) >= 9


if __name__ == "__main__":
    import gen_5v5_ridge as R, gen_5v5_canyon as C2
    # 生成并写出
    R.generate(7, "rw_5v5_ridge.tmx")
    C2.generate(7, "rw_5v5_canyon.tmx")
    # 独立解码校验
    ok1 = check("林海雪岭", "rw_5v5_ridge.tmx", R.BANDS_RECT)
    ok2 = check("赤岩裂谷", "rw_5v5_canyon.tmx", C2.BANDS_RECT)
    # 渲染带标注预览
    render_annotated("rw_5v5_ridge.tmx", "rw_5v5_ridge_preview.png", "林海雪岭", R.BANDS_RECT)
    render_annotated("rw_5v5_canyon.tmx", "rw_5v5_canyon_preview.png", "赤岩裂谷", C2.BANDS_RECT)
    print("\n独立校验:", "全部通过" if (ok1 and ok2) else "存在未达标")
