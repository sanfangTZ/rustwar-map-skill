#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片转 TMX 地图（纯地形，无单位） —— 逆向自「图片转地图_1.0.apk」

原理（与 apk 逆向结果严格对齐，com.pngtotmx.moyang）:
    1. BitmapFactory.decodeFile(path)          # 读图
    2. 逐像素 getPixel(x, y)
    3. R = Color.red(pixel)                     # 取【红色通道】0~255
    4. 按 R 值落在哪个亮度区间 -> 决定该格用哪套地形 tileset
       （apk 源码里是稀疏 switch 硬编码，见 THEME_TABLE）
    5. 生成每格 gid，写入 TMX 的 <layer>
    6. TMX 数据块编码 = base64( gzip( little-endian uint32 * N ) )
       （apk: rn_52 小端编码 -> rn_50 gzip -> rn_3360 base64）

与 apk 的差异 / 增强:
    - apk 里 gid 是"图集内部小 id"，还要经过一次渲染管线才落地；
      本脚本直接输出【可直接被铁锈战争加载】的最终 gid（对齐 gen_gids.py 体系）。
    - 支持 --size 缩放：apk 固定按原图尺寸逐格，本脚本可把图缩到 WxH 格。

用法:
    python3 png_to_tmx.py <图片路径> <输出.tmx> [--size 140x140]
                          [--theme auto|water|ice|snow|grass|stone|sand|lava]
                          [--map-name "我的图"]
                          [--no-triggers]

输出:
    - .tmx 文件（map header + tileset 段 + 数据层）
    - 控制台打印分层统计（各 gid 占比）

依赖: Pillow (PIL)。若没有，用 `pip install pillow`。
"""
import sys
import os
import io
import gzip
import base64
import struct
import argparse

# ---------------------------------------------------------------------------
# 0. 地形亮度阈值表（逆向自 apk 的稀疏 switch）
#    key = R 通道上限（不含），value = 该区间使用的"最终 gid"
#    区间依次判断：R < 第一个上限则取第一个，否则往下滚。
# ---------------------------------------------------------------------------
# apk 原始逻辑（Color.red 判定），最终 gid 已对齐 data.txt 的 firstgid：
#   R < 0x20(32)  -> 182  Water
#   R < 0x40(64)  -> 176  Shallow Water
#   R < 0x60(96)  ->  36  Ice
#   R < 0x82(130) ->  46  Snow
#   R < 0xa0(160) -> 126  Long Grass
#   R < 0xbe(190) -> 511  Stone 系列
#   R < 0xd2(210) -> 555  Sand
#   R < 0xf0(240) -> 544  Stone Lava Ridge
#   else(>=240)   -> 544
THEME_TABLE = [
    (0x20, 182, "water"),
    (0x40, 176, "shallow"),
    (0x60,  36, "ice"),
    (0x82,  46, "snow"),
    (0xa0, 126, "grass"),
    (0xbe, 511, "stone"),
    (0xd2, 555, "sand"),
    (0xf0, 544, "lava"),
    (256,  544, "lava"),
]

# ---------------------------------------------------------------------------
# 1. tileset 模板字典（逆向自 apk assets/data.txt）
#    这段在 apk 里是逐行拼进输出的，这里原样保留。
#    注意 firstgid 必须与 THEME_TABLE 里的 gid 对应，才能被铁锈正确渲染。
# ---------------------------------------------------------------------------
TILESET_HEADER = '''  <tileset firstgid="1" name="Mountain" tilewidth="20" tileheight="20" tilecount="35" columns="7">
   <image source="terrain/bitmaps/mountain.png" trans="008a76" width="140" height="100"/>
  </tileset>
  <tileset firstgid="36" name="Ice" tilewidth="20" tileheight="20" tilecount="10" columns="5">
   <image source="terrain/bitmaps/ice.png" trans="008a76" width="100" height="40"/>
  </tileset>
  <tileset firstgid="46" name="Snow" tilewidth="20" tileheight="20" tilecount="80" columns="8">
   <image source="terrain/bitmaps/snow.png" trans="008a76" width="160" height="200"/>
  </tileset>
  <tileset firstgid="126" source="terrain/Long Grass.tsx"/>
  <tileset firstgid="176" name="Shallow Water" tilewidth="20" tileheight="20" tilecount="6" columns="3">
   <image source="terrain/bitmaps/shallowwater.png" trans="008a76" width="60" height="40"/>
  </tileset>
  <tileset firstgid="182" name="Water" tilewidth="20" tileheight="20" tilecount="1" columns="1">
   <image source="terrain/bitmaps/water.png" trans="008a76" width="20" height="20"/>
  </tileset>
  <tileset firstgid="183" source="ridges/Snow Ice - Ridge.tsx"/>
  <tileset firstgid="204" name="Ice ShallowWater - Ridge" tilewidth="20" tileheight="20" tilecount="21" columns="3">
   <image source="ridges/bitmaps/ice2shallowwater_ridge.png" trans="008a76" width="60" height="140"/>
  </tileset>
  <tileset firstgid="504" source="terrain/Stone.tsx"/>
  <tileset firstgid="540" source="ridges/Stone Lava - Ridge.tsx"/>
  <tileset firstgid="555" source="terrain/Sand.tsx"/>'''

TRIGGERS_TEMPLATE = ''' <objectgroup name="Triggers">
  <object id="1" name="map_info" x="2643" y="3065" width="226" height="145">
   <properties>
    <property name="type" value="skirmish"/>
    <property name="winCondition" value="allUnitsAndBuildings"/>
   </properties>
  </object>
 </objectgroup>'''


# ---------------------------------------------------------------------------
# 2. 核心：像素 R 通道 -> gid
# ---------------------------------------------------------------------------
def r_to_gid(r, theme="auto"):
    """给定 R 通道(0-255)，返回最终 gid。
    theme != auto 时强制整张图用同一地形（调试/单主题用）。"""
    if theme != "auto":
        for _, gid, name in THEME_TABLE:
            if name == theme:
                return gid
    for limit, gid, _name in THEME_TABLE:
        if r < limit:
            return gid
    return THEME_TABLE[-1][1]


# ---------------------------------------------------------------------------
# 3. TMX 数据块编码：base64(gzip(little-endian uint32 * N))
#    与 apk 完全一致：rn_52(小端) -> rn_50(gzip) -> rn_3360(base64)
# ---------------------------------------------------------------------------
def encode_layer(gids):
    raw = struct.pack("<%dI" % len(gids), *gids)   # rn_52 小端
    comp = gzip.compress(raw, 9)                    # rn_50 gzip
    b64 = base64.b64encode(comp).decode("ascii")    # rn_3360 base64
    # 折行（TMX 惯例，每 76 字符一行，非必须但可读）
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 读图 -> gid 列表
# ---------------------------------------------------------------------------
def image_to_gids(img_path, W, H, theme="auto", auto_stretch=False,
                  bg_spread=False, bg_tol=12):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("[!] 缺少 Pillow，请先 `pip install pillow`。")

    im = Image.open(img_path).convert("RGB")
    # 缩放到目标格数（apk 是按原图逐格；这里允许指定地图尺寸）
    if (im.width, im.height) != (W, H):
        im = im.resize((W, H), Image.NEAREST)  # NEAREST 保色块边界
    px = im.load()

    # 收集全部 R 值，供 --auto-stretch 计算分位阈值
    rvals = []
    for y in range(H):
        for x in range(W):
            rvals.append(px[x, y][0])

    # 自适应拉伸：把图片【实际 R 范围 [min,max]】线性等分成 8 档，
    # 让浅色图（如白底插画）也能铺满 8 种地形。
    # 注意：这里刻意【不用】分位数——白底图 255 会严重扎堆，
    # 分位数会把多个切点挤成同一个值，导致档位不足而失效。
    # 线性等分对扎堆天然免疫，任意图片都能稳定出 8 档。
    # （apk 原始版本是固定阈值，此处为增强项，不传 --auto-stretch 时行为与 apk 一致。）
    thresholds = None
    if auto_stretch and rvals:
        lo, hi = min(rvals), max(rvals)
        if hi <= lo:
            hi = lo + 1                     # 全纯色图兜底
        span = hi - lo
        thresholds = []
        for k in range(1, 8):               # 7 个切点 -> 8 段
            thresholds.append(lo + span * k // 8)
        # 去重并保证严格递增（理论上去重后必为 7 个，兜底）
        uniq = []
        for t in thresholds:
            if not uniq or t > uniq[-1]:
                uniq.append(t)
        thresholds = uniq

    # 背景识别：找出画面中占比最高的"纯色"当作背景色。
    # 白底插画里它就是 (255,255,255)，会占掉三成以上像素。
    # --bg-spread 开启后，把这些背景像素【打散】铺满 8 种地形，
    # 前景像素才按真实亮度映射 —— 这样白底不再是单调岩浆。
    bg_color = None
    if bg_spread:
        from collections import Counter
        cnt = Counter()
        for y in range(H):
            for x in range(W):
                cnt[px[x, y]] += 1
        if cnt:
            bg_color, bg_n = cnt.most_common(1)[0]
            # 仅当该色确实占多数（>20%）才认定是背景，否则忽略
            if bg_n * 5 < W * H:
                bg_color = None

    def is_bg(c):
        if bg_color is None:
            return False
        return (abs(c[0] - bg_color[0]) <= bg_tol and
                abs(c[1] - bg_color[1]) <= bg_tol and
                abs(c[2] - bg_color[2]) <= bg_tol)

    gids = []
    stat = {}
    bg_seen = 0
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            r = c[0]
            if bg_spread and is_bg(c):
                # 背景像素：用坐标做伪随机打散，均匀铺 8 种地形，
                # 保持确定性（同一图同一结果），且不需要随机种子。
                gid = THEME_TABLE[(x * 7 + y * 13 + (x ^ y)) % 8][1]
                bg_seen += 1
            elif auto_stretch and thresholds:
                # 用动态阈值找档位（>= 最后一个切点即落最高档）
                idx = 0
                while idx < len(thresholds) and r >= thresholds[idx]:
                    idx += 1
                if idx >= len(THEME_TABLE):
                    idx = len(THEME_TABLE) - 1
                gid = THEME_TABLE[idx][1]
            else:
                gid = r_to_gid(r, theme)
            gids.append(gid)
            stat[gid] = stat.get(gid, 0) + 1
    return gids, stat


# ---------------------------------------------------------------------------
# 5. 组装 TMX
# ---------------------------------------------------------------------------
def build_tmx(gids, W, H, map_name="image_map", with_triggers=True):
    data_b64 = encode_layer(gids)
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<map version="1.0" orientation="orthogonal" renderorder="right-down"'
        f' width="{W}" height="{H}" tilewidth="20" tileheight="20"'
        ' nextobjectid="2">\n'
    )
    ts = TILESET_HEADER + "\n"
    layer = (
        f' <layer name="Ground" width="{W}" height="{H}">\n'
        '  <data encoding="base64" compression="gzip">\n'
        + data_b64 + "\n"
        '  </data>\n'
        ' </layer>\n'
    )
    # 铁锈战争还强制要求 Items(“项目”) 与 Units(“单位”) 两层
    # 纯地形地图这两层全部填 0 即可（无物品/无单位）
    empty_data = encode_layer([0] * (W * H))
    def empty_layer(nm):
        return (
            f' <layer name="{nm}" width="{W}" height="{H}">\n'
            '  <data encoding="base64" compression="gzip">\n'
            + empty_data + "\n"
            '  </data>\n'
            ' </layer>\n'
        )
    items_layer = empty_layer("Items")
    units_layer = empty_layer("Units")
    tg = (TRIGGERS_TEMPLATE + "\n") if with_triggers else ""
    return head + ts + layer + items_layer + units_layer + tg + "</map>\n"


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------
def parse_size(s):
    if "x" in s.lower():
        a, b = s.lower().split("x")
        return int(a), int(b)
    n = int(s)
    return n, n


def main():
    ap = argparse.ArgumentParser(description="图片转 TMX 地图（纯地形）")
    ap.add_argument("image", help="输入图片路径(png/jpg...)")
    ap.add_argument("out", help="输出 .tmx 路径")
    ap.add_argument("--size", default="140x140",
                    help="地图格数 WxH，默认 140x140")
    ap.add_argument("--theme", default="auto",
                    help="auto(默认) 或 water/shallow/ice/snow/grass/stone/sand/lava")
    ap.add_argument("--map-name", default="image_map", help="地图名（仅备注；图层名已固定为 Ground）")
    ap.add_argument("--no-triggers", action="store_true",
                    help="不写 Triggers 段")
    ap.add_argument("--auto-stretch", action="store_true",
                    help="自适应拉伸：把图片实际 R 范围 [min,max] 线性等分 8 档，"
                         "让浅色/白底图也能铺满全部地形（增强项，默认关=与 apk 一致）")
    ap.add_argument("--bg-spread", action="store_true",
                    help="白底/纯色背景打散：自动识别占比最高的背景色，把这些背景像素"
                         "均匀铺满 8 种地形，只让前景按亮度映射。适合白底插画/证件图")
    ap.add_argument("--bg-tol", type=int, default=12,
                    help="背景色容差(0-255)，默认 12，越大识别背景越宽松")
    args = ap.parse_args()

    if not os.path.isfile(args.image):
        sys.exit(f"[!] 找不到图片: {args.image}")

    W, H = parse_size(args.size)
    gids, stat = image_to_gids(args.image, W, H, args.theme, args.auto_stretch,
                              args.bg_spread, args.bg_tol)
    assert len(gids) == W * H

    xml = build_tmx(gids, W, H, args.map_name, not args.no_triggers)
    with open(args.out, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(xml)

    # 统计打印
    name_of = {gid: name for _, gid, name in THEME_TABLE}
    print(f"[OK] 生成 {args.out}  ({W}x{H} = {len(gids)} 格)")
    print(f"     字节数: {len(xml.encode('utf-8'))}")
    print("     地形分布:")
    for gid in sorted(stat):
        pct = stat[gid] * 100.0 / len(gids)
        print(f"       gid={gid:<4} ({name_of.get(gid,'?'):<8}) {stat[gid]:>6} 格  {pct:5.1f}%")


if __name__ == "__main__":
    main()
