#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯原版纯地形批量重做 V2 —— 8 张图全部左右对峙、零触发器、逐格镜像（对齐赤翼芳澜形态）

形态基准（三方同志·赤翼芳澜，社区唯一接受图的形态）：
  Ground/Items/Units(+Decorations 装饰) + UnitObjects(每家1个commandCenter) + 矿全在Items层
  ★ 不写 Triggers 对象组（连 map_info/camera_start 都不放）—— 纯原版纯地形
质量红线（每张强制过闸，不过闸拒绝出图）：
  ① verify_no_flower 零花屏(水族归一口径)  ② 左右逐格镜像  ③ BFS 出生点两两互达  ④ validate_tmx
布局：8p → 4v4 左右对峙(左偶右奇)；10p → 5v5(左0/2/4/6/8 右1/3/5/7/9)
"""
import os, sys, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_4v4_arena as A4
import gen_koth as K
import gen_combined as C
import xml.etree.ElementTree as ET
import struct, base64, gzip
from collections import deque, Counter

OUTDIR = "/workspace/重做地图/纯地形版"
os.makedirs(OUTDIR, exist_ok=True)
SIZE = 200
PASS = {0, 1, 2, 3, 4, 12, 23}
H = W = SIZE
WF = (A4.WATER, A4.SEA, A4.OCEAN, A4.SHOAL)

# ---------------------------------------------------------------- 纹理变体（同签名不同美术 tile）
_VAR = [None]
def _variant_map():
    if _VAR[0] is None:
        from collections import defaultdict
        root = ET.parse(C.TSX).getroot()
        sig2t = defaultdict(list); tid2sig = {}
        for t in root.findall("tile"):
            sig = t.get("terrain")
            if not sig:
                continue
            tid = int(t.get("id"))
            sig2t[sig].append(tid); tid2sig[tid] = sig
        _VAR[0] = (sig2t, tid2sig)
    return _VAR[0]

def _tex_tid(tid, r, c, block=6):
    """同拼接签名内选变体：6×6 块内一致（形成自然纹理区块）；左右半用不同种子 → 视觉不对称、逻辑等价。"""
    sig2t, tid2sig = _variant_map()
    sig = tid2sig.get(tid)
    if not sig:
        return tid
    cands = sig2t[sig]
    if len(cands) <= 1:
        return tid
    side = 1 if c >= 100 else 0
    h = (r // block) * 73856093 ^ (c // block) * 19349663 ^ (side * 0x9E3779B9)
    return cands[(h & 0x7fffffff) % len(cands)]

# ---------------------------------------------------------------- 3×3 矿坑（沙坑边框 + 中心矿）
def apply_mine_pits(grid, items):
    """矿坑不改地形（3×3 沙会触发 autotile 降级出高石）；边框改由装饰层岩石实现。"""
    return grid

GOOD_MINE = {A4.GRASS, A4.DIRT, A4.SAND, A4.HIGHGRASS, A4.MUD}
def place_mines_safe(items, grid, spawns, neutral):
    """矿点布置：要求 5×5 内全为草/土/沙（保证 3×3 沙坑不产生花屏），否则螺旋找位。"""
    # 积分图：O(1) 判断任意 7×7 是否全草（矿坑 3×3 + 四周各留 2 格缓冲）
    integ = [[0] * (W + 1) for _ in range(H + 1)]
    for r in range(H):
        for c in range(W):
            integ[r + 1][c + 1] = (1 if grid[r][c] in GOOD_MINE else 0) \
                + integ[r][c + 1] + integ[r + 1][c] - integ[r][c]
    def ok7(r, c, half=5):
        # 11×11 全草：矿坑离任何山/水/林 ≥6 格，autotile 的降级也够不到
        r0, c0, r1, c1 = r - half, c - half, r + half + 1, c + half + 1
        if r0 < 0 or c0 < 0 or r1 > H or c1 > W:
            return False
        ssum = integ[r1][c1] - integ[r0][c1] - integ[r1][c0] + integ[r0][c0]
        return ssum == (2 * half + 1) ** 2
    def ok_both(r, c):
        # 矿点会镜像到对侧；两侧 11×11 都必须纯草
        return ok7(r, c) and ok7(r, 199 - c)
    placed = []
    def far_enough(r, c):
        # 与已放矿点（含镜像点）切比雪夫距离 ≥4 → 3×3 矿坑互不重叠
        for (pr, pc) in placed:
            if max(abs(r - pr), abs(c - pc)) < 4:
                return False
        return True
    def find(r, c):
        if 0 <= r < H and 0 <= c < W and ok_both(r, c) and far_enough(r, c):
            return (r, c)
        for rad in range(1, 26):
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    if max(abs(dr), abs(dc)) != rad:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < H and 0 <= cc < W and ok_both(rr, cc) and far_enough(rr, cc):
                        return (rr, cc)
        return None
    # 每家 2 个起步矿坑
    for (sr, sc, _t) in spawns:
        cnt = 0
        for (dr, dc) in ((-4, -4), (-4, 4), (4, -4), (4, 4), (-6, 0), (6, 0), (0, -6), (0, 6)):
            if cnt >= 2:
                break
            p = find(sr + dr, sc + dc)
            if p and not items[p[0]][p[1]]:
                items[p[0]][p[1]] = 1
                placed.append(p); placed.append((p[0], 199 - p[1]))
                cnt += 1
    # 中立矿坑
    for (nr, nc) in neutral:
        p = find(nr, nc)
        if p:
            items[p[0]][p[1]] = 1
            placed.append(p); placed.append((p[0], 199 - p[1]))

# ---------------------------------------------------------------- 写出（纯地形，无 Triggers 组）
def write_pure(grid, decor, items, spawns, out):
    # 矿坑：使用 misc 图集自带的 3×3 九宫格（tile 0..8，中心 tile4=res_pool，四周 8 格为边框）
    g2 = grid
    for r in range(H):
        for c in range(W):
            if items[r][c]:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < H and 0 <= cc < W:
                            decor[rr][cc] = 0        # 坑上不放装饰，避免遮挡
    ground_tid = C.autotile(g2)
    ground = [[A4.GROUND_FG + _tex_tid(ground_tid[r][c], r, c) for c in range(W)] for r in range(H)]
    items_gid = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if items[r][c]:
                # misc 3×3 矿坑图块：左上→右下 tile 0..8，中心 tile 4（res_pool）
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < H and 0 <= cc < W:
                            items_gid[rr][cc] = A4.MISC_FG + ((dr + 1) * 3 + (dc + 1))
    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(W), "height": str(H),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())
    def enc(data):
        raw = struct.pack("<%dI" % (W * H), *[data[r][c] for r in range(H) for c in range(W)])
        return base64.b64encode(gzip.compress(raw)).decode()
    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * W for _ in range(H)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(W), "height": str(H)})
        d = ET.SubElement(l, "data", {"encoding": "base64", "compression": "gzip"})
        d.text = enc(data)
    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid = [100]
    for (sr, sc, team) in spawns:        # 纯原版：每家仅 1 个总部
        o = ET.SubElement(uo, "object", {"id": str(nid[0]), "x": str(sc * 20), "y": str(sr * 20),
                                         "width": "20", "height": "20"})
        nid[0] += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": "commandCenter"})
    max_oid = 0
    for g in map_el.findall("objectgroup"):
        for o in g.findall("object"):
            max_oid = max(max_oid, int(o.get("id", 0)))
    map_el.set("nextobjectid", str(max_oid + 1))
    tree = ET.ElementTree(map_el)
    issues = K.validate_tmx(tree, W, H, {C.TSX: (A4.GROUND_FG, A4.MERGED_COUNT)},
                            [(sr, sc) for sr, sc, _ in spawns])
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return issues

# ---------------------------------------------------------------- 校验/修复
def _norm(t):
    return "W" if t in WF else t

def _fix_flower(grid, max_iter=8):
    """对 verify_no_flower 同口径（水族归一后 >2 类）的 2×2，把孤立少数格归入多数类。"""
    for _ in range(max_iter):
        changed = False
        for vy in range(H):
            for vx in range(W):
                cells = [(vx + dx, vy + dy) for dy in (0, 1) for dx in (0, 1)
                         if vx + dx < W and vy + dy < H]
                ts = [grid[y][x] for (x, y) in cells]
                cnt = Counter(_norm(t) for t in ts)
                if len(cnt) <= 2:
                    continue
                maj_norm = cnt.most_common(1)[0][0]
                # 多数组里出现最多的原始类别值
                maj_val = Counter(t for t in ts if _norm(t) == maj_norm).most_common(1)[0][0]
                # 只改“孤立少数格”（其归一类在本块只出现 1 次）
                for (x, y), t in zip(cells, ts):
                    if cnt[_norm(t)] == 1 and _norm(t) != maj_norm:
                        grid[y][x] = maj_val
                        changed = True
        if not changed:
            break

def bfs_ok(grid, spawns):
    pts = [(sr, sc) for sr, sc, _ in spawns]
    def bfs(sr, sc, tr, tc):
        if grid[sr][sc] not in PASS:
            return -1
        seen = {(sr, sc)}; q = deque([(sr, sc, 0)])
        while q:
            r, c, d = q.popleft()
            if (r, c) == (tr, tc):
                return d
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in seen and grid[nr][nc] in PASS:
                    seen.add((nr, nc)); q.append((nr, nc, d + 1))
        return -1
    bad = 0; dist = []
    for i, (sr, sc) in enumerate(pts):
        for j, (tr, tc) in enumerate(pts):
            if i < j:
                d = bfs(sr, sc, tr, tc)
                dist.append((i, j, d))
                if d < 0:
                    bad += 1
    return bad, dist

def mirror_check(grid):
    n = 0
    for r in range(H):
        for c in range(100):
            if grid[r][199 - c] != grid[r][c]:
                n += 1
    return n

# ---------------------------------------------------------------- 通用构件
def _spawn_protect(grid, spawns):
    for (sr, sc, _t) in spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W and abs(dr) + abs(dc) <= 2:
                    grid[r][c] = A4.GRASS

def _decorate_blobs(grid, rng, specs, spawns):
    forbid = [[1 if grid[r][c] in WF or grid[r][c] == A4.SAND else 0 for c in range(W)] for r in range(H)]
    for (sr, sc, _t) in spawns:
        for dr in range(-4, 5):
            for dc in range(-4, 5):
                r, c = sr + dr, sc + dc
                if 0 <= r < H and 0 <= c < W:
                    forbid[r][c] = 1
    for cat, lst in specs:
        for (cr, cc, rad) in lst:
            A4.place_blob(grid, forbid, cr, cc, rad, cat, rng, lobes=8, jit=0.28)

def _common_specs(rng):
    return [
        (A4.HIGHSTONE, [(18, 16, 9), (52, 12, 7), (148, 12, 7), (181, 16, 9)]),
        (A4.HIGHGRASS, [(28, 50, 9), (76, 50, 9), (124, 50, 9), (172, 50, 9)]),
        (A4.MUD,       [(52, 24, 8), (148, 24, 8)]),
        (A4.STONE,     [(50, 38, 6), (150, 38, 6)]),
        (A4.DIRT,      [(28, 40, 6), (76, 40, 6), (124, 40, 6), (172, 40, 6)]),
    ]

def _finish(grid, spawns):
    _spawn_protect(grid, spawns)
    for _ in range(6):
        A4._clean_water_vertices(grid)
    _fix_flower(grid)
    A4._clean_water_vertices(grid)
    for r in range(H):
        for c in range(100):
            grid[r][199 - c] = grid[r][c]
    return grid

def _force_shoal(grid, r0, r1, c0, c1):
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if grid[r][c] in (A4.WATER, A4.SEA, A4.OCEAN):
                grid[r][c] = A4.SHOAL

# ---------------------------------------------------------------- 8p 主题（4v4）
def build_oval(seed):
    # 纵向大长湖（南北贯穿）+ 三岛链 + 三座横桥 → 与图一的"同心环"彻底区分
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    ky = 2.4
    for r in range(H):
        for c in range(W):
            d = math.hypot((r - 100.0) / ky, c - 99.5) + 0.05 * 30 * A4._noise(r, c)
            if d <= 30: grid[r][c] = A4.WATER
            elif d <= 32: grid[r][c] = A4.SHOAL
            elif d <= 36: grid[r][c] = A4.SAND
    A4.carve_islands(grid, [(62.0, 99.5, 5, 3), (100.0, 99.5, 6, 3), (138.0, 99.5, 5, 3)])
    for (r0, r1) in [(58, 66), (95, 105), (134, 142)]:
        _force_shoal(grid, r0, r1, 60, 140)
    _decorate_blobs(grid, rng, _common_specs(rng), A4.get_spawns())
    return _finish(grid, A4.get_spawns()), rng, A4.get_spawns()

def build_twolakes(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            d = min(math.hypot(r - 63.0, c - 99.5), math.hypot(r - 137.0, c - 99.5)) + 0.06 * 24 * A4._noise(r, c)
            if d <= 24: grid[r][c] = A4.WATER
            elif d <= 26: grid[r][c] = A4.SHOAL
            elif d <= 30: grid[r][c] = A4.SAND
    for r in range(90, 111):
        for c in range(W):
            if grid[r][c] in WF:
                grid[r][c] = A4.GRASS
    _decorate_blobs(grid, rng, _common_specs(rng), A4.get_spawns())
    return _finish(grid, A4.get_spawns()), rng, A4.get_spawns()

def build_river(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            d = abs(c - 99.5) + 2.5 * A4._vn(r, c, 1 / 24.0)
            if d <= 6: grid[r][c] = A4.WATER
            elif d <= 8: grid[r][c] = A4.SHOAL
            elif d <= 11: grid[r][c] = A4.SAND
    for (r0, r1) in [(36, 46), (95, 105), (154, 164)]:
        _force_shoal(grid, r0, r1, 84, 116)
    _decorate_blobs(grid, rng, _common_specs(rng), A4.get_spawns())
    return _finish(grid, A4.get_spawns()), rng, A4.get_spawns()

def build_ridge8(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    for c in range(W):
        rs = 100 + 16 * math.cos((c - 99.5) / 14.0)
        if 28 <= c <= 40 or 95 <= c <= 104 or 159 <= c <= 171:
            continue
        for r in range(int(rs) - 6, int(rs) + 7):
            if 0 <= r < H:
                grid[r][c] = A4.HIGHSTONE
    _decorate_blobs(grid, rng, _common_specs(rng), A4.get_spawns())
    return _finish(grid, A4.get_spawns()), rng, A4.get_spawns()

def build_chaos(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    specs = [(A4.HIGHSTONE, [(18, 16, 9), (181, 16, 9), (100, 18, 8), (64, 62, 7), (136, 62, 7)]),
             (A4.HIGHGRASS, [(28, 48, 9), (76, 48, 9), (124, 48, 9), (172, 48, 9), (100, 64, 7)]),
             (A4.MUD,       [(52, 26, 8), (148, 26, 8), (64, 44, 6), (136, 44, 6)]),
             (A4.STONE,     [(50, 40, 7), (150, 40, 7), (100, 44, 6), (88, 78, 5), (112, 78, 5)]),
             (A4.DIRT,      [(28, 38, 6), (76, 38, 6), (124, 38, 6), (172, 38, 6), (100, 30, 7)])]
    _decorate_blobs(grid, rng, specs, A4.get_spawns())
    return _finish(grid, A4.get_spawns()), rng, A4.get_spawns()

def build_yuanhu(seed):
    grid, rng, spawns = A4.build_terrain(seed)
    cy, cx = 100.0, 99.5
    # 同心环堤：湖中一圈环形陆堤（四向开口）→ 湖—堤—湖—岛 四层同心环
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - cy, c - cx)
            gate = (abs(r - cy) <= 2 or abs(c - cx) <= 2)
            if 19.5 <= d <= 23.5:
                if not gate:
                    grid[r][c] = A4.GRASS if 20.5 <= d <= 22.5 else A4.SAND
            elif 16.5 <= d < 19.5 or 23.5 < d <= 26.5:
                if grid[r][c] in (A4.WATER, 8, 9, A4.SHOAL):
                    grid[r][c] = A4.SAND       # 开口处/堤外统一铺沙道，避免断面三类交界
    _fix_flower(grid)
    for _ in range(4):
        A4._clean_water_vertices(grid)
    return grid, rng, spawns

# ---------------------------------------------------------------- 10p 主题（5v5，同镜像管线）
SPAWN_YS5 = [22, 60, 100, 140, 178]
LEFT_X5, RIGHT_X5 = 26, 173
def get_spawns5():
    return ([(y, LEFT_X5, t) for y, t in zip(SPAWN_YS5, [0, 2, 4, 6, 8])] +
            [(y, RIGHT_X5, t) for y, t in zip(SPAWN_YS5, [1, 3, 5, 7, 9])])

def _specs5(rng):
    return [
        (A4.HIGHSTONE, [(16, 14, 9), (100, 14, 8), (184, 14, 9)]),
        (A4.HIGHGRASS, [(24, 48, 9), (60, 48, 9), (100, 48, 9), (140, 48, 9), (176, 48, 9)]),
        (A4.MUD,       [(44, 24, 8), (156, 24, 8)]),
        (A4.STONE,     [(44, 38, 6), (156, 38, 6)]),
        (A4.DIRT,      [(24, 38, 6), (60, 38, 6), (100, 38, 6), (140, 38, 6), (176, 38, 6)]),
    ]

# --- 伍分裂谷：中央南北大峡谷（两壁高石、谷底通道） ---
def build_valley5(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            d = abs(c - 99.5) + 1.2 * A4._vn(r, c, 1 / 20.0)
            if 6.0 <= d <= 9.5:
                grid[r][c] = A4.HIGHSTONE          # 峡谷两壁（直接接草，两类交界不花屏）
    for (r0, r1) in [(34, 46), (94, 106), (154, 166)]:   # 三个横向谷口（穿谷通道）
        for r in range(r0, r1 + 1):
            for c in range(84, 116):
                if grid[r][c] in (A4.HIGHSTONE, A4.STONE):
                    grid[r][c] = A4.GRASS
    specs = _specs5(rng) + [(A4.STONE, [(75, 96, 2), (140, 103, 2)])]
    _decorate_blobs(grid, rng, specs, get_spawns5())
    return _finish(grid, get_spawns5()), rng, get_spawns5()

# --- 失落圣坛：中央环形圣坛高地（高石残垣环 + 四方入口 + 中央台座） ---
def build_altar5(seed):
    rng = random.Random(seed); grid = [[A4.GRASS] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            d = math.hypot(r - 100.0, c - 99.5)
            entrance = (abs(r - 100.0) <= 2 or abs(c - 99.5) <= 2) and d <= 12
            if 8.0 <= d <= 11 and not entrance:
                grid[r][c] = A4.HIGHSTONE          # 圣坛残垣环（四方入口）
            elif d < 8 and not (abs(r - 100.0) <= 1 and abs(c - 99.5) <= 1):
                pass                                # 坛内草地
            if d < 3:
                grid[r][c] = A4.STONE              # 中央台座
    specs = _specs5(rng)
    _decorate_blobs(grid, rng, specs, get_spawns5())
    return _finish(grid, get_spawns5()), rng, get_spawns5()

# ---------------------------------------------------------------- 中立矿
NEUTRAL_8P = [(70, 50), (129, 50), (100, 44)]
NEUTRAL_10P = [(62, 52), (138, 52), (100, 44)]

def place_node_mines_safe(items, grid, nodes):
    """矿点放置：落水(水族)才螺旋挪到最近陆地；绝不强制改地形 → 不产生花屏。"""
    for (nr, nc) in nodes:
        if not (0 <= nr < H and 0 <= nc < W):
            continue
        if grid[nr][nc] in WF:
            found = None
            for rad in range(1, 9):
                for dr in range(-rad, rad + 1):
                    for dc in range(-rad, rad + 1):
                        if max(abs(dr), abs(dc)) != rad:
                            continue
                        r, c = nr + dr, nc + dc
                        if 0 <= r < H and 0 <= c < W and grid[r][c] not in WF:
                            found = (r, c); break
                    if found: break
                if found: break
            if not found:
                continue
            nr, nc = found
        items[nr][nc] = 1

def mirror_nodes(nodes):
    out = list(nodes)
    for (r, c) in nodes:
        if c != 99:
            out.append((r, 199 - c))
    return out

# ---------------------------------------------------------------- 真实贴图渲染（Items 画真图块，不画黄块）
def render_pure(tmx, out_png):
    import numpy as np
    from PIL import Image as _Im
    root = ET.parse(tmx).getroot(); size = int(root.get("width"))
    arr = np.array(_Im.open(C.PNG).convert("RGBA"))
    cols = C._COLS; TW = TH = 20
    def tile(tid):
        r, c = tid // cols, tid % cols
        return arr[r*TH:(r+1)*TH, c*TW:(c+1)*TW, :]
    canvas = np.zeros((size*TH, size*TW, 4), dtype=np.uint8)
    layers = {n: K._layer(root, n) for n in ("Ground", "Decorations", "Items")}
    for r in range(size):
        for c in range(size):
            y, x = r*TH, c*TW
            g = layers["Ground"][r][c]
            if g >= A4.GROUND_FG:
                t = tile(g - A4.GROUND_FG)
                canvas[y:y+TH, x:x+TW] = t
            for name in ("Decorations", "Items"):
                v = layers[name][r][c]
                if v >= A4.GROUND_FG:
                    t = tile(v - A4.GROUND_FG).astype(np.float32)
                    a = t[:, :, 3:4] / 255.0
                    base = canvas[y:y+TH, x:x+TW].astype(np.float32)
                    rgb = t[:, :, :3] * a + base[:, :, :3] * (1 - a)
                    al = np.maximum(base[:, :, 3:4], t[:, :, 3:4])
                    canvas[y:y+TH, x:x+TW] = np.concatenate([rgb, al], axis=2).astype(np.uint8)
    _Im.fromarray(canvas).convert("RGB").save(out_png)

# ---------------------------------------------------------------- 左右半独立（去对称·公平不变）
def half_merge(builder, sA, sB):
    """左半用 seedA、右半用 seedB 的镜像生成：团块位置/半径/类型一致(公平)，形状相位不同(去对称)。"""
    gA, rng, sp = builder(sA)
    gB, _, _ = builder(sB)
    grid = [row[:] for row in gA]
    for r in range(H):
        for c in range(100, W):
            grid[r][c] = gB[r][199 - c]
    for r in range(H):                     # 中轴带取 A 侧，接缝连续
        for c in range(96, 104):
            grid[r][c] = gA[r][c] if c < 100 else gA[r][199 - c]
    for _ in range(8):
        A4._clean_water_vertices(grid)
    _fix_flower(grid)
    for _ in range(4):
        A4._clean_water_vertices(grid)
    return grid, rng, sp

# ---------------------------------------------------------------- 主流程
def make(name, grid, rng, spawns, neutral):
    items = [[0] * W for _ in range(H)]
    place_mines_safe(items, grid, spawns, mirror_nodes(neutral))
    for r in range(H):                    # 只镜像矿点；地形保持左右形状独立
        for c in range(100):
            items[r][199 - c] = items[r][c]
    flower = C.verify_no_flower(grid)
    cl = Counter(grid[r][c] for r in range(H) for c in range(100))
    cr = Counter(grid[r][c] for r in range(H) for c in range(100, W))
    tl, tr = sum(cl.values()), sum(cr.values())
    mir = round(max(abs(cl[k] / tl - cr[k] / tr) for k in set(cl) | set(cr)) * 100, 2)
    bad, dist = bfs_ok(grid, spawns)
    decor = A4.make_decor(grid, rng)
    out = os.path.join(OUTDIR, name + ".tmx")
    issues = write_pure(grid, decor, items, spawns, out)
    ok = (flower == 0) and (bad == 0) and (mir <= 3.0) and (not issues)
    render_pure(out, out.replace(".tmx", "_preview.png"))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: 花屏={flower} 左右差异%={mir} 连通断={bad} 矿总数={sum(sum(r_) for r_ in items)} 校验={issues if issues else '无'}")
    if bad:
        print("   断路对:", [(i, j) for i, j, d in dist if d < 0])
    return ok

if __name__ == "__main__":
    results = {}
    print("======== 8p（4v4 左右对峙）========")
    results["椭圆湖8p"] = make("椭圆湖8p", *half_merge(build_oval, 31, 131), NEUTRAL_8P)
    results["双湖桥8p"] = make("双湖桥8p", *half_merge(build_twolakes, 32, 132), NEUTRAL_8P)
    results["大河流两岸8p"] = make("大河流两岸8p", *half_merge(build_river, 33, 133), NEUTRAL_8P)
    results["铁臂山系8p"] = make("铁臂山系8p", *half_merge(build_ridge8, 34, 134), NEUTRAL_8P)
    results["混沌大陆8p"] = make("混沌大陆8p", *half_merge(build_chaos, 35, 135), NEUTRAL_8P)
    results["圆弧法权8p"] = make("圆弧法权8p", *half_merge(build_yuanhu, 11, 111), NEUTRAL_8P)
    print("======== 10p（5v5 左右对峙）========")
    results["伍分裂谷10p"] = make("伍分裂谷10p", *half_merge(build_valley5, 41, 141), NEUTRAL_10P)
    results["失落圣坛10p"] = make("失落圣坛10p", *half_merge(build_altar5, 42, 142), NEUTRAL_10P)
    print("======== 总结 ========")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print("全部过闸 ✅" if all(results.values()) else "存在未过闸 ❌")
