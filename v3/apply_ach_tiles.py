#!/usr/bin/env python3
"""把"自己画的成就石碑地块"嵌进 rw_cuba.tmx 的 atlas 末行空位，并把成就区矩形改用自定义 GID。
不动美国大陆/海洋，只改左下角成就石碑那块。"""
import base64, gzip, struct, io, os, numpy as np
from PIL import Image
import xml.etree.ElementTree as ET

# 与脚本同目录的 rw_cuba.tmx（skill 自带，随处可跑）
TMX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rw_cuba.tmx")
OUTDIR = os.path.dirname(os.path.abspath(__file__))
TW = 20

# 成就石碑矩形(格坐标, 来自 gen_cuba.carve_panel)
ACH_X0, ACH_X1, ACH_Y0, ACH_Y1 = 30, 230, 850, 1150

# ---------------------------------------------------------------------------
# 1) 画自定义 tile (20x20, RGB)
# ---------------------------------------------------------------------------
def rng_img(seed):
    return np.random.default_rng(seed)

def make_core():
    """无缝暗板岩内芯：深蓝灰底 + 低幅噪点 + 稀疏云母闪光/暗坑。
    不含任何跨格线条(避免每格重复形成花纹)，四边无缝。"""
    base = np.array([45, 60, 74], dtype=np.int16)
    r = rng_img(11)
    n = r.integers(-6, 7, size=(TW, TW))
    img = np.clip(base[None, None, :] + n[:, :, None], 0, 255).astype(np.uint8)
    # 稀疏云母闪光(亮点)与暗坑，密度极低，铺开像整块岩石而非花纹
    for _ in range(3):
        y, x = r.integers(0, TW), r.integers(0, TW)
        img[y, x] = (88, 110, 126)          # 云母闪光
    for _ in range(3):
        y, x = r.integers(0, TW), r.integers(0, TW)
        img[y, x] = (34, 46, 58)            # 暗坑
    return img

def make_frame(kind):
    """立体花岗岩石框：朝海外缘 4px 暗断崖 + 次外缘 1px 亮棱线；
    朝石板内缘 2px 亮倒角 + 边缘 2px 金色内嵌边(铭牌感)。角落两外两内。"""
    base = np.array([113, 114, 122], dtype=np.int16)
    r = rng_img(hash(kind) & 0xFFFF)
    n = r.integers(-8, 9, size=(TW, TW))
    img = np.clip(base[None, None, :] + n[:, :, None], 0, 255).astype(np.uint8)
    DARK = np.array([54, 56, 64], dtype=np.uint8)
    HI = np.array([172, 174, 182], dtype=np.uint8)
    GOLD = np.array([216, 184, 108], dtype=np.uint8)
    OUTER = {"top": ("top",), "bottom": ("bottom",), "left": ("left",), "right": ("right",),
             "tl": ("left", "top"), "tr": ("right", "top"),
             "bl": ("left", "bottom"), "br": ("right", "bottom")}[kind]
    INNER = {"top": ("bottom",), "bottom": ("top",), "left": ("right",), "right": ("left",),
             "tl": ("right", "bottom"), "tr": ("left", "bottom"),
             "bl": ("right", "top"), "br": ("left", "top")}[kind]
    def band(side, w0, w1, color):
        """在 side 边的 [w0,w1) 像素带涂色(0=最外缘)。"""
        if side == "top":    img[w0:w1, :] = color
        elif side == "bottom": img[TW - w1:TW - w0, :] = color
        elif side == "left": img[:, w0:w1] = color
        elif side == "right": img[:, TW - w1:TW - w0] = color
    for s in OUTER:
        band(s, 0, 4, DARK)                 # 暗断崖(朝海)
        band(s, 4, 5, HI)                   # 棱线高光
    for s in INNER:
        band(s, 0, 2, GOLD)                 # 金色内嵌边(朝石板)
        band(s, 2, 4, HI)                   # 亮倒角
    # 让倒角带上保留一点岩石噪感(重撒低幅噪声)
    for s in INNER:
        if s == "top":    rows = slice(2, 4)
        elif s == "bottom": rows = slice(TW - 4, TW - 2)
        elif s == "left":  cols = slice(2, 4)
        else:              cols = slice(TW - 4, TW - 2)
        if s in ("top", "bottom"):
            nn = r.integers(-5, 6, size=(rows.stop - rows.start, TW))
            reg = img[rows, :].astype(np.int16) + nn[:, :, None]
            img[rows, :] = np.clip(reg, 0, 255).astype(np.uint8)
        else:
            nn = r.integers(-5, 6, size=(TW, cols.stop - cols.start))
            reg = img[:, cols].astype(np.int16) + nn[:, :, None]
            img[:, cols] = np.clip(reg, 0, 255).astype(np.uint8)
    return img

ORDER = ["core", "tl", "top", "tr", "left", "right", "bl", "bottom", "br"]
TILES = {}
for i, k in enumerate(ORDER):
    TILES[k] = make_core() if k == "core" else make_frame(k)

# 自定义 tile 起始 id(在 atlas 末行空位). firstgid=1 => GID = id+1
START_ID = 1098
GID = {k: START_ID + i + 1 for i, k in enumerate(ORDER)}  # core->1099, tl->1100 ...

# ---------------------------------------------------------------------------
# 2) 嵌入 atlas 末行空位
# ---------------------------------------------------------------------------
t = ET.parse(TMX).getroot()
ts = t.find("tileset")
props = ts.find("properties")
emb = None
for p in props.findall("property"):
    if p.get("name") == "embedded_png":
        emb = p
atlas = Image.open(io.BytesIO(base64.b64decode(emb.get("value")))).convert("RGBA")
AW, AH = atlas.size
acols = AW // TW
arr = np.array(atlas)
for i, k in enumerate(ORDER):
    tid = START_ID + i
    col = tid % acols; row = tid // acols
    x0, y0 = col * TW, row * TW
    tile = np.array(TILES[k]).astype(np.uint8)
    rgba = np.dstack([tile, np.full((TW, TW), 255, dtype=np.uint8)])
    arr[y0:y0 + TW, x0:x0 + TW] = rgba
new_atlas = Image.fromarray(arr, "RGBA")
def _enc(im):
    b = io.BytesIO(); im.save(b, format="PNG"); return b.getvalue()
new_b64 = base64.b64encode(_enc(new_atlas)).decode("ascii")
emb.set("value", new_b64)
ts.set("tilecount", str(START_ID + len(ORDER)))

# ---------------------------------------------------------------------------
# 3) 替换地面层石碑区域 GID + 清理装饰层石碑区域
# ---------------------------------------------------------------------------
def get_layer(name):
    return [l for l in t.findall("layer") if l.get("name") == name][0]

def decode_layer(l):
    raw = gzip.decompress(base64.b64decode(l.find("data").text.strip()))
    H = int(l.get("height")); W = int(l.get("width"))
    return list(struct.unpack("<%dI" % (W * H), raw)), W, H

def encode_layer(l, data, W, H):
    packed = struct.pack("<%dI" % (W * H), *data)
    l.find("data").text = base64.b64encode(gzip.compress(packed)).decode()

g_layer = get_layer("Ground")
g, GW, GH = decode_layer(g_layer)
# 装饰层
d_layer = get_layer("Decorations")
d, DW, DH = decode_layer(d_layer)

for r in range(ACH_Y0 - 1, ACH_Y1 + 2):
    for c in range(ACH_X0 - 1, ACH_X1 + 2):
        idx = r * GW + c
        inside = (ACH_Y0 <= r <= ACH_Y1) and (ACH_X0 <= c <= ACH_X1)
        if inside:
            g[idx] = GID["core"]
        else:
            if r == ACH_Y0 - 1 and c == ACH_X0 - 1: k = "tl"
            elif r == ACH_Y0 - 1 and c == ACH_X1 + 1: k = "tr"
            elif r == ACH_Y1 + 1 and c == ACH_X0 - 1: k = "bl"
            elif r == ACH_Y1 + 1 and c == ACH_X1 + 1: k = "br"
            elif r == ACH_Y0 - 1: k = "top"
            elif r == ACH_Y1 + 1: k = "bottom"
            elif c == ACH_X0 - 1: k = "left"
            elif c == ACH_X1 + 1: k = "right"
            else: k = "core"
            g[idx] = GID[k]
        d[idx] = 0  # 清掉石碑上的装饰岩石

encode_layer(g_layer, g, GW, GH)
encode_layer(d_layer, d, DW, DH)

# 写回
ET.indent(t)
ET.ElementTree(t).write(TMX, xml_declaration=True, encoding="utf-8")
print("已写入", TMX, " tilecount->", ts.get("tilecount"))

# ---------------------------------------------------------------------------
# 4) 导出: 我画的 tile 原图 + 铺进去后的真实石碑渲染
# ---------------------------------------------------------------------------
# (a) tile 原图放大展示
SC = 6
labels = {"core": "石板内芯", "tl": "左上框", "top": "上框", "tr": "右上框",
          "left": "左框", "right": "右框", "bl": "左下框", "bottom": "下框", "br": "右下框"}
cols = 5
rows = (len(ORDER) + cols - 1) // cols
canv = Image.new("RGB", (cols * TW * SC, rows * TW * SC), (20, 20, 24))
for i, k in enumerate(ORDER):
    x = (i % cols) * TW * SC; y = (i // cols) * TW * SC
    tile = Image.fromarray(TILES[k]).resize((TW * SC, TW * SC), Image.NEAREST)
    canv.paste(tile, (x, y))
canv.save(os.path.join(OUTDIR, "ach_tiles_preview.png"))
print("已导出", os.path.join(OUTDIR, "ach_tiles_preview.png"), "(我画的自定义地块)")

# (b) 用真实 atlas 渲染石碑区域(放大) -> 看铺进去的真实效果
SC2 = 1
reg_w = (ACH_X1 + 2) - (ACH_X0 - 1); reg_h = (ACH_Y1 + 2) - (ACH_Y0 - 1)
real = Image.new("RGBA", (reg_w * TW * SC2, reg_h * TW * SC2), (0, 0, 0, 0))
arr_atlas = np.array(new_atlas)
for r in range(ACH_Y0 - 1, ACH_Y1 + 2):
    for c in range(ACH_X0 - 1, ACH_X1 + 2):
        gid = g[r * GW + c]
        tid = gid - 1
        col = tid % acols; row = tid // acols
        x0, y0 = col * TW, row * TW
        tile = arr_atlas[y0:y0 + TW, x0:x0 + TW, :3]
        rr = (r - (ACH_Y0 - 1)) * TW * SC2; cc = (c - (ACH_X0 - 1)) * TW * SC2
        # 缩放到 SC2
        t_img = Image.fromarray(tile).resize((TW * SC2, TW * SC2), Image.NEAREST)
        real.paste(t_img, (cc, rr))
real.convert("RGB").save(os.path.join(OUTDIR, "rw_cuba_ach_real.png"))
print("已导出", os.path.join(OUTDIR, "rw_cuba_ach_real.png"), "(石碑铺自定义地块后的真实渲染)")
