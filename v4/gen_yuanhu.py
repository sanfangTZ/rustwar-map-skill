#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁锈战争 1.15 —— 4V4 左右对垒竞技图《圆弧法权》V1（完全重做，抛弃旧缩放版）

设计意图（根治旧缩放版被社区骂的全部通病）：
- 【抛弃旧版】不做任何"等比缩放/重采样"，从零生成全新地形 → 旧版的"砸碎/火山口坏/高地不对/太小"全部不复存在。
- 【左右严格镜像】4v4 左右对垒：A 方(左岸 队0/2/4/6) vs B 方(右岸 队1/3/5/7)，
  地形以中轴(col≈99.5)成对生成后强制镜像，两半布局逐格等价 → 竞技公平，治"两边高地不对"。
- 【保形渲染】原生 autotile 按地形自然拼接（绝不复制/翻转镜像 hack），verify_no_flower 零花屏才出图
  → 治"整个地图被砸碎"。
- 【中央法权圣坛】居中(100,99.5)的同心圆弧结构：外圈深水护城河 → 浅滩环 → 沙滩 → 内圈法坛草地平台；
  两座浅滩海陆桥(陆军可涉+海军可过)连通左右岸到圣坛；圣坛上 2 座富矿水晶 = 全场必争"法权"要冲，
  抢到即经济优势。开阔可争夺，不是"牢房" → 治"中间没法打/牢房"。
- 【平衡】每队 2 起步矿；两岸 4 中立水晶 + 8 中立扩张矿；家↔圣坛/矿路径全程畅通 → 治"矿超标/寻路卡"。
- 尺寸 200×200 保持，不缩 → 治"太小"。

胜负：本版先做【歼灭 mainBuilings + 中央富矿争夺】（稳、可玩、竞技）。
      KOTH"占点即胜"objective 触发器另版严谨实现+实测后再合入（RW 无原生占点得分，不冒险）。

复用 gen_4v4_arena 验证过的保形/镜像/零花屏地形管线，仅重做主题、随机种子、中央命名与玩法说明。
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_4v4_arena as A          # 复用其保形/镜像/零花屏地形与资源函数
import gen_koth as K
import gen_combined as C
from PIL import Image, ImageDraw, ImageFont

SIZE = A.SIZE
GROUND_FG = A.GROUND_FG
MISC_FG = A.MISC_FG
_RES_POOL_TILE = A._RES_POOL_TILE
MERGED_COUNT = A.MERGED_COUNT

SEED = 11                            # 新种子 → 全新地形（与旧群峰环湖/旧缩放版都不同）
OUT = "/workspace/圆弧法权8p.tmx"


def generate(seed=SEED, out=OUT):
    # 1) 全新地形（保形 + 左右严格镜像 + 零花屏，全在 A.build_terrain 内保证）
    grid, rng, spawns = A.build_terrain(seed)
    items = [[0] * SIZE for _ in range(SIZE)]
    A.place_home_mines(items, grid, spawns)                         # 每队 2 起步矿
    A.place_node_mines(items, grid, A.mirror_nodes(A.EXPANSION_LEFT))  # 两岸中立扩张矿

    decor = A.make_decor(grid, rng)

    # 2) 原生 autotile 渲染 + 零花屏硬闸
    ground_tid = C.autotile(grid)
    flower_bad = C.verify_no_flower(grid)
    if flower_bad:
        raise RuntimeError("修边自检未通过(不可发布): 2×2 花屏块=%d" % flower_bad)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(SIZE)] for r in range(SIZE)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(SIZE)] for r in range(SIZE)]

    # 3) 左右严格镜像校验（竞技公平底线）：地形逐格左右等价
    mirror_mismatch = 0
    for r in range(SIZE):
        for c in range(100):
            if grid[r][199 - c] != grid[r][c]:
                mirror_mismatch += 1
    if mirror_mismatch:
        raise RuntimeError("左右镜像不对称(不可发布): 失配格=%d" % mirror_mismatch)

    # 4) 写 tmx
    import xml.etree.ElementTree as ET
    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(SIZE), "height": str(SIZE),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())

    def enc(data):
        import struct, base64, gzip
        raw = struct.pack("<%dI" % (SIZE * SIZE), *[data[r][c] for r in range(SIZE) for c in range(SIZE)])
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * SIZE for _ in range(SIZE)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(SIZE), "height": str(SIZE)})
        d = ET.SubElement(l, "data", {"encoding": "base64", "compression": "gzip"})
        d.text = enc(data)

    og = ET.SubElement(map_el, "objectgroup", {"name": "Triggers"})
    nid = [1]

    def add_obj(name, typ, x, y, props, w=20, hh=20):
        o = ET.SubElement(og, "object", {"id": str(nid[0]), "name": name, "type": typ,
                                         "x": str(x), "y": str(y), "width": str(w), "height": str(hh)})
        nid[0] += 1
        p = ET.SubElement(o, "properties")
        for k, v in props.items():
            ET.SubElement(p, "property", {"name": k, "value": str(v)})
        return o

    add_obj("map_info", "", SIZE // 2, SIZE // 2 - 20, {
        "type": "skirmish",
        "winCondition": "mainBuilings",
        "fog": "los",
        "introText": (
            "【圆弧法权 · 4v4 左右对垒】\n"
            "A方=左岸(队0/2/4/6)  vs  B方=右岸(队1/3/5/7)，左右严格对称、竞技公平。\n"
            "中央『法权圣坛』被护城河环绕，两座浅滩桥连通两岸——圣坛上的富矿水晶是全场必争要冲，抢到即经济优势。\n"
            "拆光对方生产建筑即获胜。"
        ),
    }, 224, 136)

    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid_u = [100]

    def add_unit(unit, team, x, y):
        o = ET.SubElement(uo, "object", {"id": str(nid_u[0]), "x": str(x), "y": str(y),
                                         "width": "20", "height": "20"})
        nid_u[0] += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": unit})

    # 每家：主基地 + 2 工程兵（保证 mainBuilings 开局不判负、可扩张）
    for (sr, sc, team) in spawns:
        sx, sy = sc * 20, sr * 20
        add_unit("commandCenter", team, sx, sy)
        back = 1 if sc < 100 else -1
        add_unit("builder", team, sx + back * 40, sy)
        add_unit("builder", team, sx, sy + 40)

    # 两岸中立水晶（陆地可争夺）
    for (cc, rr) in A.mirror_nodes(A.CRYSTAL_LEFT):
        add_unit("crystalResource", -1, rr * 20, cc * 20)
    # 中央法权圣坛：一对对称富矿水晶（中轴相邻 → 严格镜像）
    CENTER_CORE = [(100, 99), (100, 100)]
    for (cc, rr) in CENTER_CORE:
        add_unit("crystalResource", -1, rr * 20, cc * 20)

    add_obj("camera_start", "camera_start", 100 * 20, SIZE // 2 * 20, {}, 20, 20)

    max_oid = 0
    for g in map_el.findall("objectgroup"):
        for o in g.findall("object"):
            try:
                max_oid = max(max_oid, int(o.get("id", 0)))
            except ValueError:
                pass
    map_el.set("nextobjectid", str(max_oid + 1))

    tree = ET.ElementTree(map_el)
    fgmap = {C.TSX: (GROUND_FG, MERGED_COUNT)}
    issues = K.validate_tmx(tree, SIZE, SIZE, fgmap, [(sr, sc) for sr, sc, _t in spawns])
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, spawns, grid, items, decor, issues, flower_bad, mirror_mismatch


def annotate(tmx, out_png, spawns, grid, items):
    K.render(tmx, out_png)
    im = Image.open(out_png).convert("RGB")
    W, H = im.size
    TILE = 20
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        f_big = ImageFont.truetype(FONT, 30, index=0)
        f_mid = ImageFont.truetype(FONT, 22, index=0)
    except Exception:
        f_big = f_mid = ImageFont.load_default()
    LEFT = (225, 45, 45); RIGHT = (40, 130, 235); AXIS = (255, 200, 0)
    CRY = (0, 200, 220); MINE = (255, 210, 0); ALTAR = (0, 255, 255); BRIDGE = (255, 150, 0)
    d = ImageDraw.Draw(im)
    for (sr, sc, team) in spawns:
        cx, cy = sc * TILE, sr * TILE
        col = LEFT if sc == A.LEFT_X else RIGHT
        d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], outline=col, width=5)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=col)
        d.text((cx, cy), f"T{team}", font=f_mid, fill=(255, 255, 255), anchor="mm")
    for (cc, rr) in A.mirror_nodes(A.CRYSTAL_LEFT):
        d.ellipse([cc * TILE - 9, rr * TILE - 9, cc * TILE + 9, rr * TILE + 9], outline=CRY, width=3)
    # 中央法权圣坛（同心圆弧）
    d.ellipse([(99.5 - 37) * TILE, (100 - 37) * TILE, (99.5 + 37) * TILE, (100 + 37) * TILE], outline=(0, 220, 235), width=3)
    d.ellipse([(99.5 - 11) * TILE, (100 - 11) * TILE, (99.5 + 11) * TILE, (100 + 11) * TILE], outline=ALTAR, width=5)
    for (cc, rr) in [(100, 99), (100, 100)]:
        d.ellipse([cc * TILE - 10, rr * TILE - 10, cc * TILE + 10, rr * TILE + 10], outline=(255, 255, 0), width=4)
    for (r0, r1, c0, c1) in [(95, 105, 48, 90), (95, 105, 109, 151)]:
        d.rectangle([c0 * TILE, r0 * TILE, (c1 + 1) * TILE, (r1 + 1) * TILE], outline=BRIDGE, width=3)
    for (nr, nc) in A.mirror_nodes(A.EXPANSION_LEFT):
        d.rectangle([nc * TILE - 7, nr * TILE - 7, nc * TILE + 7, nr * TILE + 7], outline=MINE, width=3)
    ax = 99.5 * TILE
    y = 0
    while y < H:
        d.line([(ax, y), (ax, min(y + 26, H))], fill=AXIS, width=4)
        y += 46
    lx, ly, lw, lh = 24, 24, 720, 330
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([lx, ly, lx + lw, ly + lh], fill=(0, 0, 0, 180))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    d.ellipse([lx + 18, ly + 26, lx + 58, ly + 66], outline=LEFT, width=5)
    d.text((lx + 72, ly + 44), "A方 左岸 队0/2/4/6", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 18, ly + 86, lx + 58, ly + 126], outline=RIGHT, width=5)
    d.text((lx + 72, ly + 104), "B方 右岸 队1/3/5/7", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.ellipse([lx + 20, ly + 150, lx + 54, ly + 184], outline=ALTAR, width=4)
    d.text((lx + 72, ly + 166), "法权圣坛(中央富矿,两桥可达)", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.rectangle([lx + 18, ly + 206, lx + 58, ly + 216], outline=BRIDGE, width=3)
    d.text((lx + 72, ly + 206), "橙框=浅滩海陆桥(陆军涉+海军过)", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.rectangle([lx + 18, ly + 240, lx + 58, ly + 250], outline=MINE, width=3)
    d.text((lx + 72, ly + 240), "黄框=中立扩张矿(必争)", font=f_big, fill=(255, 255, 255), anchor="lm")
    d.line([(lx + 20, ly + 282), (lx + 56, ly + 282)], fill=CRY, width=4)
    d.text((lx + 72, ly + 282), "青圈=中立水晶(两岸+圣坛)", font=f_big, fill=(255, 255, 255), anchor="lm")
    im.save(out_png)


if __name__ == "__main__":
    from collections import Counter
    tree, spawns, grid, items, decor, issues, flower_bad, mirror_mismatch = generate()
    K.render(OUT, "/workspace/圆弧法权8p_preview.png")
    annotate(OUT, "/workspace/圆弧法权8p_preview.png", spawns, grid, items)
    nm = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 7: "水", 8: "海", 9: "洋", 12: "高草", 14: "高石", 23: "浅滩"}
    terr = Counter(x for row in grid for x in row)
    print(f"已生成: {OUT}  ({SIZE}x{SIZE}, 8家=4v4左右对垒, seed={SEED})")
    print("地形分布:", {nm.get(k, k): v for k, v in terr.items() if v > 0})
    nres = sum(sum(row) for row in items)
    ncry = len(A.mirror_nodes(A.CRYSTAL_LEFT)) + 2
    ndecor = sum(1 for row in decor for v in row if v)
    print(f"起步矿={len(spawns)*2}  中立扩张矿={nres-len(spawns)*2}  中立矿合计={nres}  中立水晶={ncry}  装饰={ndecor}")
    print("出生点(team,row,col):", [(t, sr, sc) for sr, sc, t in spawns])
    print(f"花屏块={flower_bad}  左右镜像失配={mirror_mismatch}  校验issues={issues}")
