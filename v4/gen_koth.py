#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 1.15 —— 8 人「中岛争夺战」(King of the Hill) 地图生成器

玩法（基于官方已验证机制）：
  - 地图中央一座富矿山头岛，放 4 个 crystalResource 水晶单位（中立 team=-1，可被任意队抢占/回收）
  - 8 支队伍从八向出生岛出发，沿放射状陆地走廊向中心推进、抢中岛
  - 城夺（换总部）：每队总部被打爆→原地刷出中立(-1)总部→任意靠近的玩家单位 native 占领转为该队
    （机制已拆官方「宾语复制器」apk + 比对 RW 1.15 本体 dex 核实，详见 SKILL.md「城夺触发器」章节）
  - 胜负：winCondition=mainBuilings（拆光所有对手的生产建筑即胜）

地形：使用用户提供的【地面层整合.tsx】完整图集（四角地形索引自动拼接）。
  - 海岸按 草→沙→浅滩→水→洋 平滑环状分层，由图集自身过渡块无缝衔接
  - 中央陆地打破单调：散布 石山(山)、土斑块、泥坑(凹陷)，并用 岩石/枯木 点缀
"""
import sys, os, math, base64, gzip, struct, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_combined as C
import xml.etree.ElementTree as ET
from PIL import Image
import numpy as np

COMBINED_COUNT = C.info()["count"]   # 1080
GROUND_FG = 1
MISC_FG = GROUND_FG + COMBINED_COUNT
_RES_POOL_TILE = 4                    # misc.tsx 中 res_pool 的 tile id (1.15 实测 id=4)
MISC_TILES = 18                        # misc.tsx 的 tile 数（水晶 res_pool + 树）
MERGED_COUNT = COMBINED_COUNT + MISC_TILES   # 合并后地面图集总格数 = 1098

def _find_misc():
    """定位 RW 标准 misc.tsx（水晶/树源）。优先用与本脚本同目录打包的 misc.tsx，
    其次退回全盘 glob（本机装了 RW 且解包过 apk 时可用）。"""
    import glob
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.path.join(here, "misc.tsx"),   # skill 自带（打包在 zip 里，任何机器都能跑）
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    here = os.path.dirname(os.path.abspath(__file__))
    res = glob.glob(os.path.join(here, "**", "misc.tsx"), recursive=True)
    return res[0] if res else None

def _find_misc_png(mt):
    """misc.tsx 对应的 png：优先 skill 自带的同级 misc.png，其次 RW 的 bitmaps/ 目录。"""
    d = os.path.dirname(mt)
    for p in (os.path.join(d, "misc.png"),            # skill 自带
              os.path.join(d, "bitmaps", "misc.png")):  # RW apk 解包布局
        if os.path.exists(p):
            return p
    return None

def _extend_ground_png():
    """若 地面层整合.png 还是 600 高（未合并），把 misc 的 18 格接到第 31 行。"""
    mt = _find_misc()
    if not mt:
        return
    mpng = _find_misc_png(mt)
    if not mpng:
        return
    im = Image.open(C.PNG).convert("RGBA")
    if im.size[1] >= (COMBINED_COUNT // C._COLS + 1) * 20 + (MISC_TILES // C._COLS) * 20:
        return  # 已合并
    misc = Image.open(mpng).convert("RGBA")
    W, H = im.size
    canvas = Image.new("RGBA", (W, H + 20))
    canvas.paste(im, (0, 0))
    for k in range(MISC_TILES):
        sx, sy = (k % 3) * 20, (k // 3) * 20
        tile = misc.crop((sx, sy, sx + 20, sy + 20))
        dx, dy = ((COMBINED_COUNT + k) % C._COLS) * 20, ((COMBINED_COUNT + k) // C._COLS) * 20
        canvas.paste(tile, (dx, dy))
    canvas.save(C.PNG)

def build_ground_tileset():
    """把 地面层整合.tsx + 标准 misc.tsx(水晶/树) 合并内联为一个 <tileset> 元素。
    图片以 <property name="embedded_png"> 内嵌（RW 1.15 认的是这个属性，不是 <image><data>）；
    水晶靠 tile 自带 res_pool 属性被识别为资源矿。结果：地图为【零外部依赖的真正单文件 .tmx】。"""
    _extend_ground_png()
    ts = ET.parse(C.TSX)
    root = ts.getroot()
    el = ET.Element("tileset", {
        "firstgid": str(GROUND_FG),
        "name": root.get("name"),
        "columns": root.get("columns"),
        "tilecount": str(MERGED_COUNT),
        "tileheight": root.get("tileheight"),
        "tilewidth": root.get("tilewidth"),
    })
    for ch in root:
        el.append(ch)
    # 图片：RW 1.15 认的是 tileset 级 <property name="embedded_png">（base64 PNG），
    # 不是 <image> 下的 <data> 子节点。两者都要给：image 只标尺寸，embedded_png 提供像素。
    b64 = base64.b64encode(open(C.PNG, "rb").read()).decode("ascii")
    img = el.find("image")
    if img is not None:
        img.clear()
        img.set("width", str(720))
        img.set("height", str(620))
        img.set("format", "png")
    props = el.find("properties")
    if props is None:
        props = ET.SubElement(el, "properties")
    for pr in list(props.findall("property")):
        if pr.get("name") == "embedded_png":
            props.remove(pr)
    ET.SubElement(props, "property", {"name": "embedded_png", "value": b64})
    # 追加 misc 的 18 格（merged tile id = COMBINED_COUNT + k），保留 res_pool / 树 属性
    mt = _find_misc()
    if mt:
        mr = ET.parse(mt).getroot()
        for tl in mr.findall("tile"):
            k = int(tl.get("id"))
            m = COMBINED_COUNT + k
            nt = ET.SubElement(el, "tile", {"id": str(m)})
            p = tl.find("properties")
            if p is not None:
                np_ = ET.SubElement(nt, "properties")
                for pr in p.findall("property"):
                    ET.SubElement(np_, "property", {"name": pr.get("name"), "value": pr.get("value") or ""})
    return el

# ---------- 地形：解析 SDF 平滑环状分层（草→沙→浅水→水→深水） ----------
def generate_koth(size=160, seed=7, teams=8):
    H = W = size
    cx, cy = W / 2, H / 2
    rng = random.Random(seed)
    Rc = W / 2 - 16
    dirs = [2 * math.pi * i / teams - math.pi / 2 for i in range(teams)]
    spawn_r = W / 2 - 15
    spawn_centers = [(cy + math.sin(a) * spawn_r, cx + math.cos(a) * spawn_r)
                     for a in dirs]

    # 多频值噪声：制造有机犬牙交错的海岸线（确定性整数 hash，可复现）
    def _hash(ix, iy):
        h = (ix * 374761393 + iy * 668265263) & 0x7fffffff
        h = (h ^ (h >> 13)) * 1274126177
        h &= 0x7fffffff
        return (h / 0x7fffffff) * 2 - 1
    def _vn(x, y, f):
        gx = x * f; gy = y * f
        ix = int(math.floor(gx)); iy = int(math.floor(gy))
        fx = gx - ix; fy = gy - iy
        ux = fx * fx * (3 - 2 * fx); uy = fy * fy * (3 - 2 * fy)
        n00 = _hash(ix, iy); n10 = _hash(ix + 1, iy)
        n01 = _hash(ix, iy + 1); n11 = _hash(ix + 1, iy + 1)
        return (n00 + (n10 - n00) * ux) + ((n01 + (n11 - n01) * ux) - (n00 + (n10 - n00) * ux)) * uy
    def _noise(r, c):
        return 0.55 * _vn(r, c, 1/24.0) + 0.30 * _vn(r, c, 1/12.0) + 0.15 * _vn(r, c, 1/6.0)

    def sdf(r, c):
        """到陆地的平滑符号距离：<0 陆地内部，>0 海里。叠加多频噪声→有机海岸。"""
        d = math.hypot(r - cy, c - cx)
        ang = math.atan2(r - cy, c - cx)
        best = d - (24 + 1.5 * math.cos(8 * ang))     # 中央花形岛（抖动减小，边缘更平滑）
        vx, vy = c - cx, r - cy
        for a0 in dirs:                                # 放射走廊（宽度向末端渐收）
            ux, uy = math.cos(a0), math.sin(a0)
            t = vx * ux + vy * uy
            perp = abs(vx * uy - vy * ux)
            k = max(0.0, min(1.0, (t - 6) / (Rc - 6)))
            w = 6.0 - 2.0 * k
            if t < 6:
                sd = math.hypot(t - 6, perp) - w
            elif t > Rc:
                sd = math.hypot(t - Rc, perp) - w
            else:
                sd = perp - w
            if sd < best:
                best = sd
        for (sr, sc) in spawn_centers:                 # 出生岛（近圆形）
            di = math.hypot(r - sr, c - sc)
            ai = math.atan2(r - sr, c - sc)
            sd = di - (9 + 0.8 * math.cos(5 * ai))
            if sd < best:
                best = sd
        return best + 3.2 * _noise(r, c)               # 有机海岸线扰动

    # 环状分层（加厚 + 插「海」层，保证相邻对图集都有过渡块）：
    #   草地(0) -> 沙(3,3) -> 浅滩(23,2) -> 水(7,4) -> 海(8,2) -> 洋(9)
    grid = [[None] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            s = sdf(r, c)
            if s <= 0:
                grid[r][c] = 0
            elif s <= 3:
                grid[r][c] = 3          # 沙
            elif s <= 5:
                grid[r][c] = 23         # 浅滩
            elif s <= 9:
                grid[r][c] = 7          # 水
            elif s <= 11:
                grid[r][c] = 8          # 海（水↔洋 的缓冲层）
            else:
                grid[r][c] = 9          # 洋

    # ---------- 打破单调：山 / 土斑块 / 凹陷 ----------
    def blob(cr, cc, rad, cat, lobes=6, jit=0.18, only_grass=True, exclude_center=0):
        for r in range(H):
            for c in range(W):
                d = math.hypot(r - cr, c - cc)
                ang = math.atan2(r - cr, c - cc)
                rr = rad * (1 + jit * math.sin(lobes * ang + rng.uniform(0, 6)))
                if d <= rr:
                    if only_grass and grid[r][c] != 0:
                        continue
                    if exclude_center and math.hypot(r - cy, c - cx) < exclude_center:
                        continue
                    grid[r][c] = cat

    # 相邻出生岛之间的「环形沙滩桥」：玩家之间不必穿中心即可互通
    for i in range(teams):
        a1 = dirs[i]; a2 = dirs[(i + 1) % teams]
        if i == teams - 1:
            a2 += 2 * math.pi
        am = (a1 + a2) / 2
        half_arc = math.radians(16)
        hw_r = 2.2
        for r in range(H):
            for c in range(W):
                if grid[r][c] not in (7, 8, 9, 23):
                    continue
                d = math.hypot(r - cy, c - cx)
                ang = math.atan2(r - cy, c - cx)
                da = (ang - am + math.pi) % (2 * math.pi) - math.pi
                sd = max(abs(d - spawn_r) - hw_r, abs(da) * spawn_r - half_arc * spawn_r)
                if sd <= 0:
                    grid[r][c] = 3      # 沙（桥核心，保证 8 岛互通）
                elif sd <= 1.3:
                    grid[r][c] = 23     # 浅滩缓冲（沙↔浅滩，与主环带同构）
                elif sd <= 3.0:
                    grid[r][c] = 7      # 水缓冲（浅滩↔水）
                elif sd <= 5.5 and grid[r][c] == 9:
                    grid[r][c] = 8      # 洋→海降级：避免水直接怼洋，保证 水↔海 相邻（图集有过渡块）

    # ---------- 后处理：清理水里孤立的浅滩碎斑（玩家视角=悬浮脏点） ----------
    # 浅滩缓冲带的意义是"贴着沙"做过渡。噪声会把零星浅滩格甩到开阔水里，
    # 周围全是水、离沙超过 2 格 —— 这些碎斑与沙带脱节，看着像瑕疵。
    # 规则：浅滩格若 Chebyshev 距离 2 内没有任何 沙(3)，降级为 水(7)。
    def _near_sand(r, c, rad=2):
        for rr in range(max(0, r - rad), min(H, r + rad + 1)):
            for cc in range(max(0, c - rad), min(W, c + rad + 1)):
                if grid[rr][cc] == 3:
                    return True
        return False
    specks = 0
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 23 and not _near_sand(r, c):
                grid[r][c] = 7
                specks += 1

    # 中央泥坑凹陷（the 凹）：缩小到半径 2，只做小点缀，避免盖住中岛富矿水晶
    blob(cy, cx, 2, 4, lobes=7, jit=0.22, only_grass=True, exclude_center=0)
    # 3 座石山（山）：分布在山头岛内圈（抖动减小，边缘更平滑）
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.6
        mr = int(cy + math.sin(a) * 11); mc = int(cx + math.cos(a) * 11)
        blob(mr, mc, 6, 2, lobes=6, jit=0.20, only_grass=True, exclude_center=4)
    # 3 片土斑块：自然泥土点缀
    for k in range(3):
        a = 2 * math.pi * k / 3 + 1.7
        dr = int(cy + math.sin(a) * 14); dc = int(cx + math.cos(a) * 14)
        blob(dr, dc, 5, 1, lobes=5, jit=0.25, only_grass=True, exclude_center=6)

    spawns = [(int(sr), int(sc)) for (sr, sc) in spawn_centers]
    return grid, (cx, cy), spawns

# ---------- 资源：每队 2 起步矿（res_pool，维持基础经济） ----------
# 注意：中岛 4 水晶是「单位」(crystalResource)，不在这里放，改由 UnitObjects 刷（见下方）。
def place_resources_koth(grid, cx, cy, spawns, size):
    items = [[0] * size for _ in range(size)]
    def land(r, c):
        return 0 <= r < size and 0 <= c < size and grid[r][c] in (0, 1, 2, 3, 4)
    # 每队出生岛 2 水晶（res_pool 矿，被动收入）：一内一外
    for (sr, sc) in spawns:
        ang = math.atan2(sr - size / 2, sc - size / 2)
        for sgn in (1, -1):
            pr = int(sr - sgn * math.sin(ang) * 4)
            pc = int(sc - sgn * math.cos(ang) * 4)
            if land(pr, pc):
                items[pr][pc] = 1
            elif land(sr, sc):
                items[sr][sc] = 1
    return items

# ---------- 装饰：岩石/枯木 overlay（透明背景，置于地面之上） ----------
def place_decor(grid, size, rng):
    decor = [[0] * size for _ in range(size)]
    rock, wood = 826, 934          # 岩石 / 枯木（透明背景道具）
    cells_stone = [(r, c) for r in range(size) for c in range(size) if grid[r][c] == 2]
    cells_mud = [(r, c) for r in range(size) for c in range(size) if grid[r][c] == 4]
    for (r, c) in cells_stone:
        if rng.random() < 0.18:
            decor[r][c] = 1 + rock
    for (r, c) in cells_mud:
        if rng.random() < 0.12:
            decor[r][c] = 1 + wood
    return decor

# ---------- 主流程 ----------
def build_koth(seed=7, size=160, teams=8, out="rw_koth.tmx"):
    rng = random.Random(seed)
    grid, (cx, cy), spawns = generate_koth(size, seed, teams)
    while len(spawns) < teams:
        spawns.append((int(cy), int(cx)))
    spawns = spawns[:teams]
    items = place_resources_koth(grid, cx, cy, spawns, size)
    decor = place_decor(grid, size, rng)

    # 自动拼接地面
    ground_tid = C.autotile(grid)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(size)] for r in range(size)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(size)] for r in range(size)]

    # XML
    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(size), "height": str(size),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(build_ground_tileset())   # 内联 地面层整合 + misc（合并为单图集，零 .tsx）

    def enc(data):
        raw = struct.pack("<%dI" % (size * size), *[data[r][c] for r in range(size) for c in range(size)])
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor), ("Items", items_gid), ("Units", [[0] * size for _ in range(size)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(size), "height": str(size)})
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

    add_obj("map_info", "", int(size / 2), int(size / 2) - 20, {
        "type": "skirmish",
        "winCondition": "mainBuilings",
        "fog": "los",
        "introText": "【中岛争夺战 KOTH】\n中岛中央 4 座水晶＝全场唯一富矿，抢到即经济碾压；拆光对手生产建筑获胜。\n\nQ群：528400691\n作者：『银杏社』___三方同志",
    }, 203, 122)

    # 关键：初始单位必须用 UnitObjects 对象组「直接」刷出（对象属性 team=队伍号, unit=单位内部名），
    # 绝不能用 unitAdd 触发。原因：
    #   1) unitAdd 是“触发”，开局第一帧的胜负判定先于触发执行，导致单位还没刷出就被判负；
    #   2) winCondition=mainBuilings 要求每队都有“主建筑”，unitAdd 不刷主基地会立刻判负。
    # 每个出生岛给 1 个 commandCenter（主基地）+ 2 个 builder（工程兵），保证开局不判负且能扩张。
    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid_u = [100]
    def add_unit(unit, team, x, y):
        o = ET.SubElement(uo, "object", {"id": str(nid_u[0]), "x": str(x), "y": str(y),
                                         "width": "20", "height": "20"})
        nid_u[0] += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": unit})
        return o

    for i, (sr, sc) in enumerate(spawns):
        sx, sy = sc * 20, sr * 20
        add_unit("commandCenter", i, sx, sy)        # 主基地：满足 mainBuilings
        add_unit("builder", i, sx + 60, sy)         # 工程兵（与主基地留出间距避免重叠）
        add_unit("builder", i, sx, sy + 60)         # 工程兵

    # 中岛 4 个水晶 = crystalResource 单位（中立 team=-1，可被任意队抢占/回收），
    # 用 UnitObjects 直接刷在中央菱形十字草地（避开中心小泥坑）。
    # 注意：水晶是单位而非 Items 层 res_pool 矿坑；crystalResource 出自 1.15 单位表。
    off = 4
    for dr, dc in ((off, 0), (-off, 0), (0, off), (0, -off)):
        r, c = int(cy) + dr, int(cx) + dc
        if not (0 <= r < size and 0 <= c < size and grid[r][c] in (0, 1, 2, 3, 4)):
            for k in range(1, off):   # 落在泥坑/水则向中心回缩到最近陆地
                rr, cc = int(cy) + dr * k // off, int(cx) + dc * k // off
                if 0 <= rr < size and 0 <= cc < size and grid[rr][cc] in (0, 1, 2, 3, 4):
                    r, c = rr, cc
                    break
        if 0 <= r < size and 0 <= c < size and grid[r][c] in (0, 1, 2, 3, 4):
            add_unit("crystalResource", -1, c * 20, r * 20)

    # 注：中岛「占点广播」已刻意移除——多人混战时多队可能同时在中岛立塔，
    # 会同时播报「X队 和 Y队 都占领了中岛」，消息迷惑。本图占点纯靠经济要地体现，
    # 胜负仍由 winCondition=mainBuilings（拆光对手生产建筑）决定。

    add_obj("camera_start", "camera_start", int(cx * 20), int(cy * 20), {}, 20, 20)

    # ---------- 城夺（换总部）触发器 ----------
    # 机制（拆官方「宾语复制器」apk + 比对 RW 1.15 本体 dex 核实）：
    #   ① 中枢检测 unitDetect(maxUnits=0, unitType=commandCenter)：本队总部所在 80×80 区域内
    #      commandCenter 数量归 0（即总部被打爆），触发下方 unitAdd；
    #   ② unitAdd(spawnUnits=commandCenter, team=-1)：在原地刷出「中立(-1)总部」；
    #   ③ team=-1 的建筑在 RW 1.15 可被任意靠近的玩家单位 native 占领（即转为该队总部）。
    # 注意：RW 1.15 触发器动作只有 event_unitAdd / event_unitRemove / event_move /
    #       event_changeCredits / event_teamTags，并不存在 apk 里那个 unitSet 类型
    #       （那是 apk 作者 Kotlin 类名，非 RW 触发），故「按队转化」直接靠中立建筑
    #       native 占领完成，无需、也不能用 unitSet。
    # 每出生岛：1 个死亡检测 + 1 个中立总部刷新（共 2×teams 个触发器对象）。
    for i, (sr, sc) in enumerate(spawns):
        hx, hy = sc * 20, sr * 20           # 与 commandCenter 同坐标（单位中心）
        dname = f"城夺_死_{i}"
        add_obj(dname, "unitDetect", hx, hy, {
            "maxUnits": 0,
            "unitType": "commandCenter",
            "resetActivationAfter": 1440,
        }, 80, 80)
        add_obj(f"城夺_刷_{i}", "unitAdd", hx, hy, {
            "spawnUnits": "commandCenter",
            "team": -1,
            "resetActivationAfter": 1440,
            "activatedBy": dname,
        }, 80, 80)

    # 修正 nextobjectid（RW 加载虽忽略，但保持正确便于 Tiled 二次编辑）
    max_oid = 0
    for og in map_el.findall("objectgroup"):
        for o in og.findall("object"):
            try:
                max_oid = max(max_oid, int(o.get("id", 0)))
            except ValueError:
                pass
    map_el.set("nextobjectid", str(max_oid + 1))

    tree = ET.ElementTree(map_el)
    fgmap = {C.TSX: (GROUND_FG, MERGED_COUNT)}
    issues = validate_tmx(tree, size, size, fgmap, spawns)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, fgmap, spawns, grid, ground, items, decor, issues

def validate_tmx(tree, w, h, fgmap, spawns):
    issues = []
    root = tree.getroot()
    segs = sorted([(fg, fg + tc) for fg, tc in fgmap.values()])
    for i in range(len(segs) - 1):
        if segs[i][1] > segs[i + 1][0]:
            issues.append(f"GID 重叠: {segs[i]} 与 {segs[i+1]}")
    for l in root.findall("layer"):
        d = l.find("data")
        raw = base64.b64decode(d.text.strip())
        try:
            buf = gzip.decompress(raw)
        except Exception as e:
            issues.append(f"层 {l.get('name')} gzip 解压失败: {e}")
            continue
        g = struct.unpack("<%dI" % (len(buf) // 4), buf)
        maxg = max(g) if g else 0
        top = max(fg + tc for fg, tc in fgmap.values())
        if maxg >= top:
            issues.append(f"层 {l.get('name')} 含越界 GID {maxg} (上限 {top})")
    return issues

def render(tmx, out_png):
    """用整合图集渲染地面 + 装饰预览（中岛 crystalResource 水晶用青色标记）。"""
    root = ET.parse(tmx).getroot(); size = int(root.get("width"))
    im = np.array(Image.open(C.PNG).convert("RGBA"))
    cols = C._COLS; TW = TH = 20
    def tile_img(tid):
        r = tid // cols; c = tid % cols
        return im[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :3].copy()
    canvas = np.zeros((size * TH, size * TW, 3), dtype=np.uint8)
    # Ground
    data = _layer(root, "Ground"); decor = _layer(root, "Decorations"); items = _layer(root, "Items")
    for r in range(size):
        for c in range(size):
            g = data[r][c]
            if g >= GROUND_FG:
                tid = g - GROUND_FG
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = tile_img(tid)
            dg = decor[r][c]
            if dg >= GROUND_FG:
                ov = tile_img(dg - GROUND_FG)
                mask = (ov.sum(2) > 10)
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW][mask] = ov[mask]
            if items[r][c] >= MISC_FG:
                canvas[r * TH + 6:r * TH + 14, c * TW + 6:c * TW + 14] = (255, 210, 0)
    # 中岛水晶单位（crystalResource）标青色块
    uo = root.find("objectgroup[@name='UnitObjects']")
    if uo is not None:
        for o in uo.findall("object"):
            u = o.find("properties/property[@name='unit']")
            if u is not None and u.get("value") == "crystalResource":
                cc = int(int(o.get("x", 0)) // TW); rr = int(int(o.get("y", 0)) // TH)
                canvas[rr * TH + 4:rr * TH + 16, cc * TW + 4:cc * TW + 16] = (0, 200, 220)
    Image.fromarray(canvas).save(out_png)

def _layer(root, name):
    for l in root.findall("layer"):
        if l.get("name") == name:
            raw = base64.b64decode(l.find("data").text.strip())
            buf = gzip.decompress(raw)
            g = struct.unpack("<%dI" % (len(buf) // 4), buf)
            size = int(root.get("width"))
            return [list(g[i * size:(i + 1) * size]) for i in range(size)]
    return None

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--teams", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="rw_koth.tmx")
    a = ap.parse_args()
    tree, fgmap, spawns, grid, ground, items, decor, issues = build_koth(a.seed, a.size, a.teams, a.out)
    png = a.out.replace(".tmx", "_preview.png")
    render(a.out, png)
    small = a.out.replace(".tmx", "_preview_small.png")
    im = Image.open(png); im.thumbnail((900, 900)); im.save(small)
    # 统计
    from collections import Counter
    terr = Counter()
    for row in grid:
        for v in row:
            terr[v] += 1
    nm = {0: "草", 3: "沙", 23: "浅滩", 7: "水", 9: "洋", 1: "土", 2: "石", 4: "泥"}
    print(f"已生成: {a.out}  ({a.size}x{a.size}, {a.teams} 队, seed={a.seed})")
    print("地形分布(角索引→数量):", {nm.get(k, k): v for k, v in terr.items() if v > 0})
    nres = sum(1 for row in items for v in row if v)          # res_pool 起步矿
    nrock = sum(1 for row in decor for v in row if v)
    ncry = 0
    uo = tree.getroot().find("objectgroup[@name='UnitObjects']")
    if uo is not None:
        ncry = sum(1 for o in uo.findall("object")
                   if (o.find("properties/property[@name='unit']")) is not None
                   and o.find("properties/property[@name='unit']").get("value") == "crystalResource")
    print(f"起步矿(res_pool): {nres}  中岛水晶(crystalResource): {ncry}  装饰(岩石/枯木): {nrock}")
    print(f"出生点: {spawns}")
    print(f"预览图: {png} / {small}")
    if issues:
        print("⚠ 校验问题:");
        for i in issues: print("   -", i)
    else:
        print("✅ 静态校验通过")
