#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁锈战争 1.15 —— 『古巴导弹危机(IF线)』大战场地图生成器 (RW 1.15)

设计(基于用户设定 + 官方已验证机制)：
  - 地图形状：由用户提供的「北美洲」参考图程序化抽陆地掩膜(蓝=水,其余=陆)。
    参考图是手机截图(上下带黑边搜索框)，故 build_mask 先按"含蓝色海洋的行/列范围"
    自动裁掉 UI 黑边，只保留中间干净的地图本体，再等比缩放到大战场尺寸。
  - 美国(team=0)：每个重要城市 = 1 个 commandCenter(总部/可城夺) + 1 个 extractor(资源提取)
    + Items 层 res_pool 矿(被动收入)；华盛顿(首都)额外 +2 builder + 本土核弹发射井(民兵)。
    共 10 城 = 10 个可争夺的总部，形成"逐城沦陷"的大战场。
  - 苏联(team=1)：左侧(太平洋)大片海军——航母/战列舰/潜艇/战机 + 1 个 seaFactory(主建筑)
    + 周期增援波(自西向东持续压境)。(用户已认可此兵力，原样保留并随地图等比铺开)
  - 古巴：南部独立小岛(程序化强制生成，保证存在)，中立 team=-1 总部(可占领) + 2 个 extractor
    + 核弹发射井(中立，谁占谁得核打击) + 中立钱箱，作为真正的前线基地。
  - 加勒比中立钱箱：海上若干 team=-1 creditsCrates，经济争夺点。
  - 触发器(全部已验证)：
      · 开局注资：美/苏各 unitDetect(主建筑存在,minUnits=1,activatedBy=changeCredits +15000)
        → 核弹造价11000，必须给玩家启动资金才能买得起(用 changeCredits 而非 room 覆盖的 startingCredits)
      · 苏联持续经济：海军工厂存在期间 period unitDetect → changeCredits +1500/15秒
      · 每个美国城市 unitDetect(maxUnits=0, commandCenter, globalMessage) → "X沦陷！"，
        并 activatedBy 刷出中立总部(城夺：可被任意靠近单位占领转为该队)，形成逐城争夺
      · 美国首都 unitDetect(maxUnits=0, commandCenter, globalMessage, activatedBy=苏联全面进攻波)
        → 首都陷落 + 苏军总攻增援
      · 古巴 unitDetect(中立总部归零, globalMessage, activatedBy=苏军加钱12000+刷小飞机+刷核弹发射井)
        → 古巴沦陷后苏联获经济援助、战机增援与美洲前沿核打击能力(呼应标题)
  - 胜负：winCondition=mainBuilings（拆光/夺光对手主建筑即胜）。
"""
import sys, os, math, base64, gzip, struct, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_koth import (build_ground_tileset, C, GROUND_FG, MISC_FG,
                      _RES_POOL_TILE, MERGED_COUNT, validate_tmx)
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 北美参考图：与本脚本同目录打包（skill 自带，任何机器都能跑）。
IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "na.jpg")
# 大战场尺寸：约原 600x800 的 1.4 倍线性，形成真正的"大战场"
W, H = 820, 1160

# 地形类别(角索引)：0草 1土 2石(山) 3沙 4泥 7水 8海 9洋 23浅滩 —— 与整合图集一致
CAT_GRASS, CAT_SAND, CAT_SHOAL, CAT_WATER, CAT_STONE = 0, 3, 23, 7, 2
CAT_SEA, CAT_OCEAN = 8, 9   # 海(中等深度)/洋(最深)，用于太平洋等海洋深浅分层

# ---------------------------------------------------------------------------
# 1) 读图 → 自动裁掉 UI 黑边 → 陆地掩膜（全向量化，支持大图）
# ---------------------------------------------------------------------------
def _longest_run(mask):
    """返回布尔序列里最长连续 True 段的 (start, end)。"""
    best = (0, 0); s = e = 0
    for i, v in enumerate(mask):
        if v:
            if s == 0: s = i
            e = i
        else:
            if e - s > best[1] - best[0]: best = (s, e)
            s = e = 0
    if e - s > best[1] - best[0]: best = (s, e)
    return best

def build_mask():
    im = Image.open(IMG).convert("RGB")
    arr = np.asarray(im).astype(int)
    ih, iw, _ = arr.shape
    R, G, B = arr[..., 0], arr[..., 1], arr[..., 2]
    blue = (B > R) & (B > G) & (B > 90)
    blue_row = blue.mean(axis=1)
    blue_col = blue.mean(axis=0)
    # 真实地图本体 = 「最长连续含蓝行/列」。北美图四周环海，每行每列都含大量蓝；
    # 顶部黑搜索框(蓝=0)、底部页脚(蓝≈0)以及页脚里孤立的蓝色下载按钮(短蓝带)
    # 都不在这条连续带内，被天然排除 —— 不会再把手机 UI 拖进地图。
    TH = 0.05
    rs, re = _longest_run(blue_row > TH)   # 地图上下界
    cs, ce = _longest_run(blue_col > TH)   # 地图左右界
    if re <= rs or ce <= cs:
        crop = im
    else:
        # 内缩几像素，避开最外缘抗锯齿描边(仍属海洋/陆地，不影响版式)
        y0, y1 = rs + 6, re - 6
        x0, x1 = cs + 6, ce - 6
        crop = im.crop((x0, y0, x1 + 1, y1 + 1))
    crop = crop.resize((W, H), Image.LANCZOS)
    a = np.asarray(crop).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    land = ~((np.minimum(np.minimum(R, G), B) >= 235) | ((B > R) & (B > G) & (B > 90)))
    return land.tolist()

# ---------------------------------------------------------------------------
# 2) 距离变换 + 环状分层 + 碎斑清理（与 600x800 版同算法，尺寸无关）
# ---------------------------------------------------------------------------
def bfs_dist(sources, blocked):
    dist = [[-1] * W for _ in range(H)]
    from collections import deque
    q = deque()
    for (r, c) in sources:
        dist[r][c] = 0
        q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and dist[nr][nc] == -1 and not blocked(nr, nc):
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))
    return dist

def components(land):
    seen = [[False] * W for _ in range(H)]
    comps = []
    for r in range(H):
        for c in range(W):
            if land[r][c] and not seen[r][c]:
                cells = []
                from collections import deque
                q = deque([(r, c)]); seen[r][c] = True
                while q:
                    rr, cc = q.popleft(); cells.append((rr, cc))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < H and 0 <= nc < W and land[nr][nc] and not seen[nr][nc]:
                            seen[nr][nc] = True; q.append((nr, nc))
                comps.append(cells)
    return comps

def build_terrain(land):
    # 小陆块(<30)清成水；小水洞(<15)填成陆
    comps = components(land)
    small_land = set()
    for cells in comps:
        if len(cells) < 30:
            for (r, c) in cells:
                small_land.add((r, c))
    for (r, c) in small_land:
        land[r][c] = False
    water_comps = components([[not land[r][c] for c in range(W)] for r in range(H)])
    hole = set()
    for cells in water_comps:
        if len(cells) < 15:
            for (r, c) in cells:
                hole.add((r, c))
    for (r, c) in hole:
        land[r][c] = True

    land_boundary = [(r, c) for r in range(H) for c in range(W)
                     if land[r][c] and any(not land[r + dr][c + dc]
                                           for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                                           if 0 <= r + dr < H and 0 <= c + dc < W)]
    water_boundary = [(r, c) for r in range(H) for c in range(W)
                      if not land[r][c] and any(land[r + dr][c + dc]
                                                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                                                if 0 <= r + dr < H and 0 <= c + dc < W)]
    dland = bfs_dist(land_boundary, lambda r, c: not land[r][c])
    dwater = bfs_dist(water_boundary, lambda r, c: land[r][c])

    grid = [[CAT_WATER] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if land[r][c]:
                ld = dland[r][c]
                grid[r][c] = CAT_SAND if (ld is not None and ld <= 1) else CAT_GRASS
            else:
                wd = dwater[r][c]
                # 由岸向海做深浅分层：浅滩→水→海→洋，太平洋等大洋呈现明显深度渐变
                if wd is not None and wd <= 2:
                    grid[r][c] = CAT_SHOAL      # 浅滩(贴岸)
                elif wd is not None and wd <= 5:
                    grid[r][c] = CAT_WATER      # 水
                elif wd is not None and wd <= 11:
                    grid[r][c] = CAT_SEA        # 海(中等深度)
                else:
                    grid[r][c] = CAT_OCEAN      # 洋(最深)

    rng = random.Random(15)
    for _ in range(60):
        cr = rng.randint(20, H - 20); cc = rng.randint(20, W - 20)
        if grid[cr][cc] == CAT_GRASS:
            rad = rng.randint(1, 3)
            for r in range(cr - rad, cr + rad + 1):
                for c in range(cc - rad, cc + rad + 1):
                    if 0 <= r < H and 0 <= c < W and grid[r][c] == CAT_GRASS and (r - cr) ** 2 + (c - cc) ** 2 <= rad * rad:
                        grid[r][c] = CAT_STONE

    def near_sand(r, c, rad=2):
        for rr in range(max(0, r - rad), min(H, r + rad + 1)):
            for cc2 in range(max(0, c - rad), min(W, c + rad + 1)):
                if grid[rr][cc2] == CAT_SAND:
                    return True
        return False
    specks = 0
    for r in range(H):
        for c in range(W):
            if grid[r][c] == CAT_SHOAL and not near_sand(r, c):
                grid[r][c] = CAT_WATER
                specks += 1
    return grid, specks

def add_relief(grid, cities, cuba):
    """真实山链版地形起伏：落基山/喀斯喀特-内华达/阿巴拉契亚三条蜿蜒山链 +
    加拿大地盾与阿拉斯加的碎山高地 + 马德雷山脉。山链沿曲线随机粗细、留山口，
    不再是竖直高斯带。仅在草地上落山(石=2)，避开各总部/古巴/夏威夷。"""
    excl = set()
    for (_, x, y) in cities:
        for dr in range(-5, 6):
            for dc in range(-5, 6):
                excl.add((y + dr, x + dc))
    for dr in range(-9, 10):
        for dc in range(-9, 10):
            excl.add((cuba[1] + dr, cuba[0] + dc))

    def chain_pts(pts, step=1.6):
        """控制点(比例坐标) -> 密集折线点(格坐标)，带轻微随机摆动让山链蜿蜒。"""
        rng = random.Random(2024)
        out = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            ax, ay = x1 * W, y1 * H
            bx, by = x2 * W, y2 * H
            d = math.hypot(bx - ax, by - ay)
            n = max(2, int(d / step))
            for i in range(n):
                t = i / n
                # Catmull-Rom 风格平滑 + 垂直摆动
                px = ax + (bx - ax) * t + rng.uniform(-2.2, 2.2)
                py = ay + (by - ay) * t + rng.uniform(-2.2, 2.2)
                out.append((px, py))
        return out

    def stamp_chain(pts, width, gap=0.10):
        """沿链落山：粗细随距离变化、随机留山口(gap)，边缘撒山麓碎石。"""
        rng = random.Random(len(pts) * 31 + int(width * 100))
        for (px, py) in chain_pts(pts):
            if rng.random() < gap:            # 山口：链上留缺口供行军通过
                continue
            r = width * (0.75 + 0.85 * rng.random())
            for dr in range(-int(r) - 1, int(r) + 2):
                for dc in range(-int(r) - 1, int(r) + 2):
                    yy, xx = int(py) + dr, int(px) + dc
                    if not (0 <= yy < H and 0 <= xx < W):
                        continue
                    if (yy, xx) in excl or grid[yy][xx] != CAT_GRASS:
                        continue
                    d2 = dr * dr + dc * dc
                    if d2 <= r * r * (0.75 + 0.25 * rng.random()):
                        grid[yy][xx] = CAT_STONE
                    elif d2 <= (r + 3.5) ** 2 and rng.random() < 0.13:
                        grid[yy][xx] = CAT_STONE   # 山麓碎石

    def patch_region(fx0, fx1, fy0, fy1, n, rmin, rmax, seed, dens=0.75):
        """碎山高地(地盾/阿拉斯加)：区域内撒随机石斑。"""
        rng = random.Random(seed)
        for _ in range(n):
            cx = rng.uniform(fx0, fx1) * W
            cy = rng.uniform(fy0, fy1) * H
            r = rng.uniform(rmin, rmax)
            for dr in range(-int(r) - 1, int(r) + 2):
                for dc in range(-int(r) - 1, int(r) + 2):
                    yy, xx = int(cy) + dr, int(cx) + dc
                    if not (0 <= yy < H and 0 <= xx < W):
                        continue
                    if (yy, xx) in excl or grid[yy][xx] != CAT_GRASS:
                        continue
                    if dr * dr + dc * dc <= r * r and rng.random() < dens:
                        grid[yy][xx] = CAT_STONE

    # 落基山：北起加拿大(班夫)纵贯蒙大拿/怀俄明/科罗拉多，南入新墨西哥
    stamp_chain([(0.445, 0.185), (0.420, 0.255), (0.402, 0.325), (0.415, 0.395),
                 (0.448, 0.455), (0.432, 0.515), (0.452, 0.585)], 3.0)
    # 喀斯喀特+内华达山脉：紧贴西海岸内侧(西雅图/旧金山/洛杉矶以东)
    stamp_chain([(0.388, 0.255), (0.376, 0.325), (0.386, 0.395), (0.398, 0.460)], 2.1)
    # 阿巴拉契亚：佛蒙特→宾州→阿巴拉契亚→阿拉巴马，东北-西南走向
    stamp_chain([(0.592, 0.310), (0.572, 0.360), (0.550, 0.412), (0.528, 0.462),
                 (0.512, 0.510)], 2.1)
    # 马德雷山脉(墨西哥)：西南走向短链
    stamp_chain([(0.445, 0.585), (0.468, 0.640), (0.455, 0.700)], 1.9)
    # 加拿大地盾：北部广域碎山高地
    patch_region(0.40, 0.64, 0.075, 0.245, 34, 2.0, 4.6, 77, dens=0.62)
    # 阿拉斯加山地：西北角碎山
    patch_region(0.10, 0.34, 0.055, 0.20, 20, 1.8, 3.8, 78, dens=0.55)

# ---------------------------------------------------------------------------
# 3) 关键点（用"地图比例坐标"定义，尺寸无关 → 等比放大自动跟随）
#    格式: (名称, fx, fy)  fx/fy ∈ (0,1) 为占整图宽/高比例
# ---------------------------------------------------------------------------
# 美国重要城市（东海岸/中部/西海岸都有，覆盖全美）
US_CITIES = [
    ("西雅图", 0.365, 0.330), ("旧金山", 0.358, 0.400), ("洛杉矶", 0.360, 0.440),
    ("芝加哥", 0.520, 0.385), ("休斯顿", 0.470, 0.500), ("新奥尔良", 0.500, 0.525),
    ("华盛顿", 0.578, 0.450), ("纽约", 0.605, 0.400), ("波士顿", 0.618, 0.355),
    ("迈阿密", 0.592, 0.560),
    ("夏威夷", 0.215, 0.470),   # 太平洋前哨群岛(主岛设总部)；按真实地理在加州西南外海，较原版上移
]
CAPITAL = "华盛顿"
# 夏威夷群岛中心(比例坐标)；compute_layout 会在该处强制盖群岛，主岛落美国总部
HAWAII_FRAC = (0.215, 0.470)
# 苏联太平洋舰队（左侧=西太平洋，自北向南铺开，随图等比）
USSR_FLEET = [
    ("experiementalCarrier", 0.070, 0.290), ("experiementalCarrier", 0.105, 0.420),
    ("battleShip", 0.058, 0.355), ("battleShip", 0.092, 0.500), ("battleShip", 0.070, 0.625),
    ("attackSubmarine", 0.050, 0.420), ("attackSubmarine", 0.085, 0.580),
    ("c_interceptor", 0.072, 0.255), ("c_interceptor", 0.105, 0.550), ("c_interceptor", 0.060, 0.700),
    ("bomber", 0.082, 0.340), ("bomber", 0.100, 0.480),
    ("builderShip", 0.072, 0.460),                 # 苏军海上工程兵
    ("seaFactory", 0.082, 0.400),                  # 苏军主建筑(海军工厂,水上)
]
# 古巴：南部独立小岛(强制生成，保证存在)。地理上在佛州正南偏东
CUBA_FRAC = (0.800, 0.625)
# 加勒比/墨西哥湾中立钱箱(creditsCrates, team=-1)
NEUTRAL_CRATES_FRAC = [(0.540, 0.560), (0.560, 0.600), (0.620, 0.585), (0.585, 0.545)]

# 苏联持续增援波：太平洋舰队每隔一段时间自西向东补兵(周期 unitAdd, 帧数≈秒×60)
USSR_PERIODIC = [
    ("missileship",      0.060, 0.470, 5400),   # 导弹舰, ~90秒
    ("heavyBattleship",  0.052, 0.540, 3600),   # 重型战列, ~60秒
    ("c_interceptor",    0.045, 0.330, 3000),   # 拦截机, ~50秒
    ("attackSubmarine",  0.070, 0.660, 4800),   # 潜艇, ~80秒
]

# 苏联溃灭古巴后"变强"：经济援助(加钱) + 一波小飞机(拦截机) + 古巴岛核弹井
USSR_REINFORCE_CREDITS = 12000
USSR_REINFORCE_PLANES = [
    ("c_interceptor", 0.120, 0.290), ("c_interceptor", 0.140, 0.360), ("c_interceptor", 0.120, 0.430),
    ("c_interceptor", 0.140, 0.500), ("c_interceptor", 0.120, 0.570), ("c_interceptor", 0.140, 0.640),
]
USSR_REINFORCE_NUKE_UNIT = "nukeLauncherC"   # 落点吸附到古巴岛陆地

# 经济：核弹造价 11000，必须用 changeCredits(多人房不会被 room 设置覆盖)
US_START_CREDITS   = 15000
USSR_START_CREDITS = 15000
USSR_TICK_CREDITS  = 1500
USSR_TICK_PERIOD   = 900    # ~15秒一拨

# ---------------------------------------------------------------------------
# 成就系统：左下角"成就石碑" + 事件触发成就
#   机制(仿经典成就图)：unitDetect 监听里程碑事件 → globalMessage 全屏播报成就；
#   达成后给该阵营发奖励资金 + 在石碑上"点亮"一座队伍色奖杯(builder)。
#   面板本身是一块 carved 在海洋里的草地石碑，常驻显示成就清单。
# ---------------------------------------------------------------------------
# 成就石碑矩形(左下角海洋中，避开苏军舰队与美/古陆地)
ACH_X0, ACH_X1, ACH_Y0, ACH_Y1 = 30, 230, 850, 1150

# 成就清单：id / 阵营 / 标题 / 解锁方(0美 1苏) / 奖励资金 / 面板行 / 检测条件
#   det: unitDetect 属性(不含 x/y/w/h/reset)；scope: city:名称 | us_land | global
ACHIEVEMENTS = [
    # —— 苏联(team=1) ——
    dict(id="sov_first", side="苏联", title="初登美洲·攻占首座美国城市", team=1, credit=2000, row=0,
         det=dict(unitType="commandCenter", team=1, minUnits=1), scope="us_land"),
    dict(id="sov_seattle", side="苏联", title="西进序曲·攻占西雅图", team=1, credit=2000, row=1,
         det=dict(unitType="commandCenter", team=1, minUnits=1), scope="city:西雅图"),
    dict(id="sov_ny", side="苏联", title="帝国门户·攻占纽约", team=1, credit=3000, row=2,
         det=dict(unitType="commandCenter", team=1, minUnits=1), scope="city:纽约"),
    dict(id="sov_dc", side="苏联", title="斩首行动·攻占华盛顿", team=1, credit=5000, row=3,
         det=dict(unitType="commandCenter", team=1, minUnits=1), scope="city:华盛顿"),
    dict(id="sov_all", side="苏联", title="星条旗落地·攻占全境", team=1, credit=10000, row=4,
         det=dict(unitType="commandCenter", team=1, minUnits=12), scope="global"),
    # —— 美国(team=0) ——
    dict(id="us_shipyard", side="美国", title="击沉红海军·摧毁苏海军工厂", team=0, credit=3000, row=5,
         det=dict(unitType="seaFactory", team=1, maxUnits=0), scope="global"),
    dict(id="us_carrier", side="美国", title="航母杀手·击沉全部苏航母", team=0, credit=3000, row=6,
         det=dict(unitType="experiementalCarrier", team=1, maxUnits=0), scope="global"),
    dict(id="us_battleship", side="美国", title="战列坟场·击沉全部苏战列", team=0, credit=2500, row=7,
         det=dict(unitType="battleShip", team=1, maxUnits=0), scope="global"),
    dict(id="us_sub", side="美国", title="潜艇猎手·击沉全部苏潜艇", team=0, credit=2500, row=8,
         det=dict(unitType="attackSubmarine", team=1, maxUnits=0), scope="global"),
]

# ---------------------------------------------------------------------------
# 4) 布局计算：把比例坐标落到实际网格并吸附最近陆地/水
# ---------------------------------------------------------------------------
def snap_land(grid, gx, gy, rad=120):
    if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] in (CAT_GRASS, CAT_SAND):
        return gx, gy
    from collections import deque
    q = deque([(gx, gy)]); seen = {(gx, gy)}
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= ny < H and 0 <= nx < W and (nx, ny) not in seen:
                if grid[ny][nx] in (CAT_GRASS, CAT_SAND):
                    return nx, ny
                seen.add((nx, ny))
                if abs(nx - gx) + abs(ny - gy) <= rad:
                    q.append((nx, ny))
    return gx, gy

def snap_water(grid, gx, gy, rad=160):
    """海军单位吸附到最近水域(水/浅滩/海/洋)：草=0 沙=3 浅滩=23 水=7 石=2 海=8 洋=9"""
    WATER = {CAT_WATER, CAT_SHOAL, CAT_SEA, CAT_OCEAN}
    if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] in WATER:
        return gx, gy
    from collections import deque
    q = deque([(gx, gy)]); seen = {(gx, gy)}
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= ny < H and 0 <= nx < W and (nx, ny) not in seen:
                if grid[ny][nx] in WATER:
                    return nx, ny
                seen.add((nx, ny))
                if abs(nx - gx) + abs(ny - gy) <= rad:
                    q.append((nx, ny))
    return gx, gy

def stamp_island(grid, gx, gy, rx, ry):
    """在 (gx,gy) 盖一座椭圆小岛：草芯 + 沙岸，保证核心可落点。"""
    for r in range(gy - ry - 1, gy + ry + 2):
        for c in range(gx - rx - 1, gx + rx + 2):
            if 0 <= r < H and 0 <= c < W:
                dx, dy = (c - gx) / rx, (r - gy) / ry
                d = dx * dx + dy * dy
                if d <= 1.0:
                    grid[r][c] = CAT_GRASS
                elif d <= 1.7:
                    grid[r][c] = CAT_SAND

def carve_cuba(grid, gx, gy):
    """在 (gx,gy) 强制挖出古巴岛(草芯+沙岸)，保证始终存在且可落点。"""
    stamp_island(grid, gx, gy, 9, 4)

def carve_hawaii(grid, gx, gy):
    """在太平洋上盖夏威夷群岛：一座主岛(放总部) + 若干小岛。"""
    stamp_island(grid, gx, gy, 7, 3)                       # 主岛
    for dx, dy, rx, ry in ((-20, -7, 3, 2), (17, 5, 3, 2),
                            (5, 15, 2, 2), (-11, 17, 2, 2),
                            (22, -10, 2, 2)):
        stamp_island(grid, gx + dx, gy + dy, rx, ry)

def carve_panel(grid):
    """在左下角海洋里刻出一块"成就石碑"矩形草地(外圈 1 格石框，内为草地)，
    既作为成就清单的常驻载体，也供解锁奖杯(builder)落脚。"""
    for r in range(ACH_Y0 - 1, ACH_Y1 + 2):
        for c in range(ACH_X0 - 1, ACH_X1 + 2):
            if 0 <= r < H and 0 <= c < W:
                if ACH_Y0 <= r <= ACH_Y1 and ACH_X0 <= c <= ACH_X1:
                    grid[r][c] = CAT_GRASS
                else:
                    grid[r][c] = CAT_STONE   # 石碑外框(石)

def compute_layout(grid, seed=7):
    rng = random.Random(seed)
    # 先在美国西海岸外的太平洋上盖夏威夷群岛(主岛放总部)，确保后续城市吸附落到岛上
    hgx, hgy = int(HAWAII_FRAC[0] * W), int(HAWAII_FRAC[1] * H)
    carve_hawaii(grid, hgx, hgy)
    # 美国城市
    cities = []
    for (n, fx, fy) in US_CITIES:
        gx, gy = int(fx * W), int(fy * H)
        gx, gy = snap_land(grid, gx, gy)
        cities.append((n, gx, gy))
    cap = next((x, y) for (n, x, y) in cities if n == CAPITAL)
    # 古巴：先尝试自动识别南部独立岛；找不到就在固定比例位置强制挖岛
    comps = components([[grid[r][c] in (CAT_GRASS, CAT_SAND) for c in range(W)] for r in range(H)])
    main = max(comps, key=len)
    cand = []
    for comp in comps:
        if comp is main:
            continue
        my = sum(r for r, c in comp) / len(comp)
        mx = sum(c for r, c in comp) / len(comp)
        if my > H * 0.50 and mx > W * 0.45:
            cand.append((mx, my, comp))
    if cand:
        cand.sort(key=lambda t: -t[0])
        _, _, cubacomp = cand[0]
        cuba = (int(sum(c for r, c in cubacomp) / len(cubacomp)),
                int(sum(r for r, c in cubacomp) / len(cubacomp)))
    else:
        cgx, cgy = int(CUBA_FRAC[0] * W), int(CUBA_FRAC[1] * H)
        cuba = (cgx, cgy)
    # 无论自动识别还是强制生成，都在中心落一笔，保证核岛核心是实打实的草地
    # (避免质心恰好落在浅滩/沙岸边缘，导致总部/核弹井"浮在水里")
    carve_cuba(grid, cuba[0], cuba[1])
    cuba = (cuba[0], cuba[1])
    # 苏联舰队（吸附到水）
    fleet = []
    for (u, fx, fy) in USSR_FLEET:
        gx, gy = int(fx * W), int(fy * H)
        gx, gy = snap_water(grid, gx, gy)
        fleet.append((u, gx, gy))
    # 中立钱箱（吸附陆地岸，保证可见可捡）
    crates = []
    for (fx, fy) in NEUTRAL_CRATES_FRAC:
        gx, gy = int(fx * W), int(fy * H)
        gx, gy = snap_land(grid, gx, gy)
        crates.append((gx, gy))
    return cities, cap, cuba, fleet, crates

# ---------------------------------------------------------------------------
# 5) 组装地图
# ---------------------------------------------------------------------------
def build(out="rw_cuba.tmx", seed=7):
    land = build_mask()
    grid, specks = build_terrain(land)
    cities, cap, cuba, fleet, crates = compute_layout(grid, seed)
    add_relief(grid, cities, cuba)   # 美国本土+加拿大山地起伏(落基山/阿巴拉契亚/地盾)
    carve_panel(grid)                 # 左下角"成就石碑"矩形陆地(常驻成就面板载体)

    # 资源点(Items)：每城市 1 个 res_pool + 古巴 2 个 res_pool
    items = [[0] * W for _ in range(H)]
    for (_, x, y) in cities:
        items[y][x] = 1
    items[cuba[1]][cuba[0]] = 1
    items[cuba[1]][cuba[0] + 1] = 1

    # 装饰：陆地撒少量岩石/枯木
    decor = [[0] * W for _ in range(H)]
    dec_tiles = C.rock_tiles(200) or [826]
    land_cells = [(r, c) for r in range(H) for c in range(W) if grid[r][c] == CAT_GRASS]
    for (r, c) in random.Random(seed).sample(land_cells, min(len(land_cells), 1800)):
        if random.Random(r * 31 + c).random() < 0.03:
            decor[r][c] = GROUND_FG + random.Random(r + c).choice(dec_tiles)

    ground_tid = C.autotile(grid)
    ground = [[GROUND_FG + ground_tid[r][c] for c in range(W)] for r in range(H)]
    items_gid = [[MISC_FG + _RES_POOL_TILE if items[r][c] else 0 for c in range(W)] for r in range(H)]

    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(W), "height": str(H),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(build_ground_tileset())

    def enc(data):
        raw = struct.pack("<%dI" % (W * H), *[data[r][c] for r in range(H) for c in range(W)])
        return base64.b64encode(gzip.compress(raw)).decode()

    for name, data in [("Ground", ground), ("Decorations", decor), ("Items", items_gid), ("Units", [[0] * W for _ in range(H)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(W), "height": str(H)})
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

    add_obj("map_info", "", W // 2, H // 2 - 20, {
        "type": "skirmish",
        "winCondition": "mainBuilings",
        "fog": "explored",
        "introText": "【古巴导弹危机 · IF线 · 大战场】\n1962，苏联因与古巴结盟，得以将太平洋舰队开赴美洲西岸向美国施压！\n"
                     "- 双方开局即获战争资金(各15000，核弹造价11000)，核武立等可取。\n"
                     "- 美军：10 座本土城市 + 夏威夷群岛前哨，每处皆为「总部+资源点」，华盛顿是首都并部署本土核武(民兵)；城市可被占领/城夺。\n"
                     "- 苏军：西侧太平洋舰队自西向东压境、持续增援；古巴为苏联盟友的前线基地(含核弹发射井)，是苏军立足美洲的支点。\n"
                     "- 加勒比中立钱箱是经济争夺点(古巴本身不可争夺)。\n"
                     "- 美国首都陷落将招来苏联全面进攻。\n拆光/夺光对手主建筑(总部/海军工厂)即胜。\n\nQ群：528400691\n作者：三方同志",
    }, 203, 122)

    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid_u = [100]
    def add_unit(unit, team, gx, gy):
        o = ET.SubElement(uo, "object", {"id": str(nid_u[0]), "x": str(gx * 20), "y": str(gy * 20),
                                          "width": "20", "height": "20"})
        nid_u[0] += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": unit})
        return o

    # 美国：每城 总部 + 提取器；华盛顿额外 工兵×2 + 核弹发射井
    for (n, x, y) in cities:
        add_unit("commandCenter", 0, x, y)
        add_unit("extractor", 0, x, y)
    capx, capy = cap
    add_unit("builder", 0, capx + 3, capy)
    add_unit("builder", 0, capx, capy + 3)
    add_unit("nukeLauncherC", 0, capx - 1, capy)   # 华盛顿旁核弹发射井(民兵)

    # 古巴：苏联同盟(team=1)的前线基地 —— 正因为古巴与苏联结盟，苏军舰队才得以开赴美洲西岸。
    # 古巴不可争夺(非中立)，加勒比钱箱仍为中立可争夺。
    add_unit("commandCenter", 1, cuba[0], cuba[1])
    add_unit("extractor", 1, cuba[0], cuba[1] + 1)
    add_unit("extractor", 1, cuba[0] + 1, cuba[1])
    add_unit("nukeLauncherC", 1, cuba[0] - 1, cuba[1])   # 古巴核弹发射井(苏联盟友)
    for (x, y) in crates:
        add_unit("creditsCrates", -1, x, y)

    # 苏军舰队
    for (u, x, y) in fleet:
        add_unit(u, 1, x, y)

    add_obj("camera_start", "camera_start", capx * 20, capy * 20, {}, 20, 20)

    # ---- 标地名(mapText 常驻显示，每个总部旁标注名称) ----
    # 东部城市密集，逐城错开标签方位，避免互相压字
    LBL = {"波士顿": (-46, -34), "纽约": (22, -12), "华盛顿": (24, 6),
           "芝加哥": (-58, -6), "迈阿密": (10, 14)}
    for (n, x, y) in cities:
        col = "#ff5b5b" if n == "华盛顿" else "#ffe14d"
        ox, oy = LBL.get(n, (-12, -30))
        add_obj(f"标_{n}", "mapText", x * 20, y * 20, {
            "text": n, "textColor": col, "textSize": 18,
            "textOffsetX": ox, "textOffsetY": oy,
        }, 20, 20)
    add_obj("标_古巴", "mapText", cuba[0] * 20, cuba[1] * 20, {
        "text": "古巴(苏联)", "textColor": "#ff8a4d", "textSize": 18,
        "textOffsetX": -12, "textOffsetY": -30,
    }, 20, 20)

    # ---- 开局注资(changeCredits，多人房不会被 room 设置覆盖) ----
    # 链方向铁律：检测器(无 activatedBy,开局即激活) → 效果器(activatedBy=检测器名)
    add_obj("美_启动金检", "unitDetect", (capx - 1) * 20, (capy - 1) * 20, {
        "minUnits": 1, "unitType": "commandCenter", "team": 0,
        "width": 80, "height": 80, "resetActivationAfter": 99999,
    }, 80, 80)
    add_obj("美_启动金", "changeCredits", 0, 0, {
        "team": 0, "credits": US_START_CREDITS, "add": "true", "resetActivationAfter": 99999,
        "activatedBy": "美_启动金检",
    }, 20, 20)
    fx, fy = int(0.082 * W), int(0.400 * H)   # seaFactory 比例坐标
    fx, fy = next(((x, y) for (u, x, y) in fleet if u == "seaFactory"), (fx, fy))
    add_obj("苏_启动金检", "unitDetect", (fx - 1) * 20, (fy - 1) * 20, {
        "minUnits": 1, "unitType": "seaFactory", "team": 1,
        "width": 80, "height": 80, "resetActivationAfter": 99999,
    }, 80, 80)
    add_obj("苏_启动金", "changeCredits", 0, 0, {
        "team": 1, "credits": USSR_START_CREDITS, "add": "true", "resetActivationAfter": 99999,
        "activatedBy": "苏_启动金检",
    }, 20, 20)
    add_obj("苏_经济检", "unitDetect", (fx - 1) * 20, (fy - 1) * 20, {
        "minUnits": 1, "unitType": "seaFactory", "team": 1,
        "width": 80, "height": 80, "resetActivationAfter": USSR_TICK_PERIOD,
    }, 80, 80)
    add_obj("苏_经济", "changeCredits", 0, 0, {
        "team": 1, "credits": USSR_TICK_CREDITS, "add": "true", "resetActivationAfter": USSR_TICK_PERIOD,
        "activatedBy": "苏_经济检",
    }, 20, 20)

    # ---- 逐城沦陷 + 城夺(总部被打爆 → 刷中立总部可占领) ----
    for (n, x, y) in cities:
        if n == CAPITAL:
            continue  # 首都单独处理(触发总攻)
        add_obj(f"失_{n}", "unitDetect", (x - 1) * 20, (y - 1) * 20, {
            "maxUnits": 0, "unitType": "commandCenter",
            "width": 80, "height": 80, "globalMessage": f"{n}沦陷！",
            "resetActivationAfter": 99999,
        }, 80, 80)
        add_obj(f"城夺_刷_{n}", "unitAdd", x * 20, y * 20, {
            "spawnUnits": "commandCenter", "team": -1,
            "width": 80, "height": 80, "resetActivationAfter": 1440,
            "activatedBy": f"失_{n}",
        }, 80, 80)

    # 首都：commandCenter 归零 => 首都陷落 + 苏联全面进攻(大波增援)
    for i, (u, fx2, fy2) in enumerate([
        ("experiementalCarrier", 0.110, 0.330), ("experiementalCarrier", 0.140, 0.470),
        ("heavyBattleship", 0.125, 0.400), ("heavyBattleship", 0.150, 0.540),
        ("bomber", 0.135, 0.360), ("bomber", 0.155, 0.500), ("c_interceptor", 0.160, 0.320),
    ]):
        nm = f"首都_苏{i}"
        gx, gy = int(fx2 * W), int(fy2 * H)
        gx, gy = snap_water(grid, gx, gy)
        add_obj(nm, "unitAdd", gx * 20, gy * 20, {
            "spawnUnits": u, "team": 1, "resetActivationAfter": 99999,
            "activatedBy": "失_首都",
        }, 20, 20)
    add_obj("失_首都", "unitDetect", (capx - 1) * 20, (capy - 1) * 20, {
        "maxUnits": 0, "unitType": "commandCenter",
        "width": 100, "height": 100, "globalMessage": "华盛顿陷落！苏联发动全面进攻！",
        "resetActivationAfter": 99999,
    }, 100, 100)
    # 首都陷落 → 刷出中立总部(可占领)，使华盛顿成为可争夺节点(供"斩首行动"成就判定苏军实际占领)
    add_obj("城夺_刷_首都", "unitAdd", capx * 20, capy * 20, {
        "spawnUnits": "commandCenter", "team": -1,
        "width": 100, "height": 100, "resetActivationAfter": 1440,
        "activatedBy": "失_首都",
    }, 100, 100)

    # 注：古巴现为苏联盟友(team=1)，不可争夺，故不再设"古巴沦陷"城夺/援军链；
    # 其核弹发射井与基地自开局即归苏联，作为苏军美洲支点。

    # 苏联持续增援波
    for (u, fx2, fy2, period) in USSR_PERIODIC:
        gx, gy = int(fx2 * W), int(fy2 * H)
        gx, gy = snap_water(grid, gx, gy)
        add_obj(f"苏援_{u}", "unitAdd", gx * 20, gy * 20, {
            "spawnUnits": u, "team": 1, "resetActivationAfter": period,
        }, 20, 20)

    # ---- 天雷特效演示(非比寻常式：高空炮塔下落途中删除=天上霹雷) ----
    # 纯演出，无伤害/经济。落点选在太平洋上空空海处；unitRemove 只删 turret 且区域小，安全。
    # 想关掉本效果，删掉下面这个 for 循环即可。
    for (sx, sy) in [(0.30, 0.18), (0.60, 0.13), (0.46, 0.08)]:
        gx, gy = int(sx * W), int(sy * H)
        tag = f"{int(sx*100)}_{int(sy*100)}"
        add_obj(f"天雷刷_{tag}", "unitAdd", gx * 20, gy * 20, {
            "spawnUnits": "turret*1(falling=true,offsetHeight=1400)",
            "team": -1, "resetActivationAfter": 99999,
        }, 20, 20)
        add_obj(f"天雷删_{tag}", "unitRemove", gx * 20, gy * 20, {
            "spawnUnits": "turret", "team": -1, "delay": 40,
            "resetActivationAfter": 99999,
        }, 40, 40)

    # ---- 成就系统(仿经典成就图：左下角石碑 + 事件触发 globalMessage 播报) ----
    # 石碑标题与说明(mapText 常驻)
    add_obj("成就榜标题", "mapText", (ACH_X0 + 8) * 20, (ACH_Y0 + 10) * 20, {
        "text": "成就殿堂 · 古巴危机", "textColor": "#ffd24d", "textSize": 18,
        "textOffsetX": 0, "textOffsetY": 0,
    }, 20, 20)
    add_obj("成就榜说明", "mapText", (ACH_X0 + 8) * 20, (ACH_Y0 + 30) * 20, {
        "text": "达成条件见解锁弹窗，奖杯亮于石碑", "textColor": "#bdbdbd", "textSize": 13,
    }, 20, 20)
    city_by_name = {n: (x, y) for (n, x, y) in cities}
    for a in ACHIEVEMENTS:
        ry = 890 + a["row"] * 26
        col = "#ff8a4d" if a["team"] == 1 else "#5bd6ff"
        add_obj(f"成就标_{a['id']}", "mapText", (ACH_X0 + 16) * 20, ry * 20, {
            "text": f"【{a['side']}】{a['title']}", "textColor": col, "textSize": 15,
        }, 20, 20)
        # 检测区域
        if a["scope"] == "global":
            rx, ry0, rw, rh = 0, 0, W * 20, H * 20
        elif a["scope"] == "us_land":
            xs = [x for (_, x, y) in cities]; ys = [y for (_, x, y) in cities]
            rx = (min(xs) - 35) * 20; ry0 = (min(ys) - 35) * 20
            rw = (max(xs) - min(xs) + 70) * 20; rh = (max(ys) - min(ys) + 70) * 20
        else:  # city:名称
            nm = a["scope"].split(":", 1)[1]; gx, gy = city_by_name[nm]
            rx = (gx - 25) * 20; ry0 = (gy - 25) * 20; rw = 50 * 20; rh = 50 * 20
        # 解锁链(方向铁律)：成就检测器(无 activatedBy,开局激活,条件满足才弹窗)
        #   → 奖励资金 activatedBy=检测器 → 奖杯 activatedBy=检测器
        add_obj(f"成就_{a['id']}", "unitDetect", rx, ry0, {
            **a["det"], "width": rw, "height": rh,
            "globalMessage": f"【{a['side']}成就】{a['title']}！",
            "globalMessage_textColor": "#ffd24d" if a["team"] == 1 else "#5bd6ff",
            "resetActivationAfter": 99999,
        }, rw, rh)
        add_obj(f"成就_{a['id']}_rw", "changeCredits", 0, 0, {
            "team": a["team"], "credits": a["credit"], "add": "true",
            "resetActivationAfter": 99999,
            "activatedBy": f"成就_{a['id']}",
        }, 20, 20)
        trx, try_ = ACH_X0 + 8, 890 + a["row"] * 26
        add_obj(f"成就_{a['id']}_tr", "unitAdd", trx * 20, try_ * 20, {
            "spawnUnits": "builder", "team": a["team"], "resetActivationAfter": 99999,
            "activatedBy": f"成就_{a['id']}",
        }, 20, 20)

    # nextobjectid 修正
    max_oid = 0
    for og2 in map_el.findall("objectgroup"):
        for o in og2.findall("object"):
            try:
                max_oid = max(max_oid, int(o.get("id", 0)))
            except ValueError:
                pass
    map_el.set("nextobjectid", str(max_oid + 1))

    tree = ET.ElementTree(map_el)
    fgmap = {C.TSX: (GROUND_FG, MERGED_COUNT)}
    issues = validate_tmx(tree, W, H, fgmap, [(capy, capx)])
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return tree, issues, cities, cuba, fleet, crates

# ---------------------------------------------------------------------------
def render(tmx, out_png, cities, cuba, fleet, crates):
    root = ET.parse(tmx).getroot()
    land = build_mask(); grid, _ = build_terrain(land)
    im = np.array(Image.open(C.PNG).convert("RGBA"))
    cols = C._COLS; TW = TH = 20
    def tile_img(tid):
        r = tid // cols; c = tid % cols
        return im[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :3].copy()
    canvas = np.zeros((H * TH, W * TW, 3), dtype=np.uint8)
    def lay(name):
        for l in root.findall("layer"):
            if l.get("name") == name:
                raw = base64.b64decode(l.find("data").text.strip())
                g = struct.unpack("<%dI" % (len(gzip.decompress(raw)) // 4), gzip.decompress(raw))
                return [list(g[i * W:(i + 1) * W]) for i in range(H)]
    data = lay("Ground"); decor = lay("Decorations"); items = lay("Items")
    for r in range(H):
        for c in range(W):
            g = data[r][c]
            if g >= GROUND_FG:
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = tile_img(g - GROUND_FG)
            dg = decor[r][c]
            if dg >= GROUND_FG:
                ov = tile_img(dg - GROUND_FG)
                mask = (ov.sum(2) > 10)
                canvas[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW][mask] = ov[mask]
            if items[r][c] >= MISC_FG:
                canvas[r * TH + 6:r * TH + 14, c * TW + 6:c * TW + 14] = (255, 210, 0)
    for (n, x, y) in cities:
        col = (255, 0, 0) if n == "华盛顿" else (255, 230, 0)
        canvas[y * TH + 4:y * TH + 16, x * TW + 4:x * TW + 16] = col
    canvas[cuba[1] * TH + 4:cuba[1] * TH + 16, cuba[0] * TW + 4:cuba[0] * TW + 16] = (255, 120, 60)  # 古巴=苏联橙
    for (u, x, y) in fleet:
        canvas[y * TH + 5:y * TH + 15, x * TW + 5:x * TW + 15] = (180, 80, 255)
    for (x, y) in crates:
        canvas[y * TH + 5:y * TH + 15, x * TW + 5:x * TW + 15] = (255, 215, 0)
    # 先缩到可视尺寸，再在缩略图上叠加中文地名(避免先画字再缩小导致文字缩没)
    im = Image.fromarray(canvas)
    maxw = 1500
    sc = 1.0
    if im.width > maxw:
        sc = maxw / im.width
        im = im.resize((maxw, int(im.height * sc)))
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
    for (n, x, y) in cities:
        col = (255, 90, 90) if n == "华盛顿" else (255, 225, 90)
        draw.text((x * TW * sc + 6, y * TH * sc - 24), n, font=font, fill=col)
    draw.text((cuba[0] * TW * sc + 6, cuba[1] * TH * sc - 24), "古巴(苏)", font=font, fill=(255, 150, 90))
    # 成就石碑面板(左下角)：外框 + 标题 + 成就清单
    px0, py0 = ACH_X0 * TW * sc, ACH_Y0 * TH * sc
    px1, py1 = (ACH_X1 + 1) * TW * sc, (ACH_Y1 + 1) * TH * sc
    draw.rectangle([px0, py0, px1, py1], outline=(255, 210, 80), width=3)
    draw.text((px0 + 4, py0 + 4), "成就殿堂·古巴危机", font=font, fill=(255, 210, 80))
    for a in ACHIEVEMENTS:
        ry = (890 + a["row"] * 26) * TH * sc
        col = (255, 138, 77) if a["team"] == 1 else (91, 214, 255)
        draw.text((px0 + 10, ry), f"【{a['side']}】{a['title']}", font=font, fill=col)
    im.save(out_png)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/rw_cuba.tmx")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    tree, issues, cities, cuba, fleet, crates = build(a.out, a.seed)
    png = a.out.replace(".tmx", "_preview.png")
    render(a.out, png, cities, cuba, fleet, crates)
    print(f"已生成: {a.out}  ({W}x{H})")
    print(f"预览图: {png}")
    print("城市:", [(n, x, y) for (n, x, y) in cities])
    print("古巴:", cuba, " 舰队数:", len(fleet), " 钱箱:", len(crates))
    if issues:
        print("⚠ 校验问题:")
        for i in issues: print("   -", i)
    else:
        print("✅ 静态校验通过")
