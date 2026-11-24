# -*- coding: utf-8 -*-
"""
八张纯地形竞技图 · 全新引擎
============================
铁律（来自图集实测）：
  1) 图集只有“两类地形”过渡块（651 个签名，全部 2 类）→ 任何 2×2 最多 2 类（水族归一）。
  2) 高石只能接 草/石；高草只能接 草/泥/水；雪只能接 草/土/石/泥；浅滩只接 沙/水。
  3) 因此：区域用「条带 / 同心环」（无三岔拓扑）铺设；点状地物用 blob 且彼此间隔 ≥1 格。
"""
import os, sys, math, random, struct, base64, gzip
import xml.etree.ElementTree as ET
from collections import Counter, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_combined as C
import gen_koth as K
import gen_4v4_arena as A4

GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SNOW = 5
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14
GROUND_FG, MISC_FG, _RES_POOL = A4.GROUND_FG, A4.MISC_FG, A4._RES_POOL_TILE
WAT = {WATER, SEA, OCEAN, SHOAL}
PASS = {GRASS, DIRT, STONE, SAND, MUD, SNOW, HIGHGRASS, SHOAL}

NM = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 5: "雪", 7: "水", 8: "海",
      9: "洋", 12: "高草", 14: "高石", 23: "浅滩"}


# ============================================================ 画布引擎
class CV:
    def __init__(self, n, base):
        self.n = n
        self.base = base
        self.g = [[base] * n for _ in range(n)]
        self.blk = [[0] * n for _ in range(n)]

    def inb(self, r, c):
        return 0 <= r < self.n and 0 <= c < self.n

    # ---------------- 隔离标记 ----------------
    def mark(self, gap=1, cells=None):
        n = self.n
        if cells is None:
            # 标记所有非底色的格子 + 其 gap 邻域
            cells = [(r, c) for r in range(n) for c in range(n) if self.g[r][c] != self.base]
        for r, c in cells:
            for dr in range(-gap, gap + 1):
                for dc in range(-gap, gap + 1):
                    rr, cc = r + dr, c + dc
                    if self.inb(rr, cc):
                        self.blk[rr][cc] = 1

    def unmark(self):
        self.blk = [[0] * self.n for _ in range(self.n)]

    # ---------------- 基础形状 ----------------
    def disc(self, cy, cx, rad, cat, only=None, blk_ok=True):
        cells = []
        n = self.n
        for r in range(max(0, int(cy - rad - 1)), min(n, int(cy + rad + 2))):
            for c in range(max(0, int(cx - rad - 1)), min(n, int(cx + rad + 2))):
                if blk_ok and self.blk[r][c]:
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                if (r - cy) ** 2 + (c - cx) ** 2 <= rad * rad:
                    cells.append((r, c))
        for r, c in cells:
            self.g[r][c] = cat
        return cells

    def blob(self, cy, cx, rad, cat, rng, lobes=7, jit=0.26, only=None, blk_ok=True, squash=1.0):
        """多瓣有机斑块（squash>1 纵向拉长）。"""
        ph = [rng.uniform(0, math.tau) for _ in range(lobes)]
        amp = [rng.uniform(0.65, 1.25) for _ in range(lobes)]
        cells = []
        n = self.n
        R = rad * 1.4 + 2
        for r in range(max(0, int(cy - R * squash - 1)), min(n, int(cy + R * squash + 2))):
            for c in range(max(0, int(cx - R - 1)), min(n, int(cx + R + 2))):
                if blk_ok and self.blk[r][c]:
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                dy, dx = (r - cy) / squash, c - cx
                d = math.hypot(dy, dx)
                a = math.atan2(dy, dx)
                k = sum(amp[i] * math.cos(lobes * a + ph[i]) for i in range(lobes)) / lobes
                if d <= rad * (1 + jit * k):
                    cells.append((r, c))
        for r, c in cells:
            self.g[r][c] = cat
        return cells

    def band_h(self, r0, r1, cat, c0=None, c1=None, only=None, blk_ok=False):
        n = self.n
        c0 = 0 if c0 is None else c0
        c1 = n - 1 if c1 is None else c1
        cells = []
        for r in range(max(0, r0), min(n, r1 + 1)):
            for c in range(max(0, c0), min(n, c1 + 1)):
                if blk_ok and self.blk[r][c]:
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                self.g[r][c] = cat
                cells.append((r, c))
        return cells

    def band_v(self, c0, c1, cat, r0=None, r1=None, only=None, blk_ok=False):
        n = self.n
        r0 = 0 if r0 is None else r0
        r1 = n - 1 if r1 is None else r1
        cells = []
        for c in range(max(0, c0), min(n, c1 + 1)):
            for r in range(max(0, r0), min(n, r1 + 1)):
                if blk_ok and self.blk[r][c]:
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                self.g[r][c] = cat
                cells.append((r, c))
        return cells

    def ring(self, cy, cx, r_in, r_out, cat, gates=(), only=None):
        """圆环（gates=[(angle_deg, half_width_deg), ...] 处断开）。"""
        cells = []
        n = self.n
        for r in range(max(0, int(cy - r_out - 1)), min(n, int(cy + r_out + 2))):
            for c in range(max(0, int(cx - r_out - 1)), min(n, int(cx + r_out + 2))):
                d = math.hypot(r - cy, c - cx)
                if not (r_in <= d <= r_out):
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                if gates:
                    ang = math.degrees(math.atan2(r - cy, c - cx)) % 360
                    if any(abs((ang - ga + 180) % 360 - 180) <= gw for ga, gw in gates):
                        continue
                self.g[r][c] = cat
                cells.append((r, c))
        return cells

    def rect(self, r0, r1, c0, c1, cat, only=None):
        cells = []
        n = self.n
        for r in range(max(0, r0), min(n, r1 + 1)):
            for c in range(max(0, c0), min(n, c1 + 1)):
                if only is not None and self.g[r][c] not in only:
                    continue
                self.g[r][c] = cat
                cells.append((r, c))
        return cells

    # ---------------- 变形 ----------------
    def snap_mirror(self):
        """结构镜像兜底（左半为准）——保证公平。"""
        n = self.n
        for r in range(n):
            for c in range(n // 2, n):
                self.g[r][c] = self.g[r][n - 1 - c]

    def count(self):
        return Counter(v for row in self.g for v in row)


# ============================================================ 校验 & 修补
def nf(grid):
    """官方口径花屏块数（水族归一）。"""
    return C.verify_no_flower(grid)


def fix_gently(grid, it=6):
    """软修复：只把 2×2 中的孤立少数格并入多数（不放大花屏）。"""
    H, W = len(grid), len(grid[0])

    def canon(t):
        return 70 if t in WAT else t
    for _ in range(it):
        ch = False
        for r in range(H - 1):
            for c in range(W - 1):
                ts = [grid[r][c], grid[r][c + 1], grid[r + 1][c], grid[r + 1][c + 1]]
                cnt = Counter(canon(t) for t in ts)
                if len(cnt) <= 2:
                    continue
                maj = cnt.most_common(1)[0][0]
                majval = Counter(t for t in ts if canon(t) == maj).most_common(1)[0][0]
                for i, (rr, cc) in enumerate([(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)]):
                    if cnt[canon(ts[i])] == 1 and canon(ts[i]) != maj:
                        grid[rr][cc] = majval
                        ch = True
        if not ch:
            break
    return grid


def bfs_pairs(grid, spawns):
    H, W = len(grid), len(grid[0])
    pts = [(sr, sc) for sr, sc, _ in spawns]

    def go(s, t):
        if grid[s[0]][s[1]] not in PASS or grid[t[0]][t[1]] not in PASS:
            return -1
        seen = {s}
        q = deque([(s[0], s[1], 0)])
        while q:
            r, c, d = q.popleft()
            if (r, c) == t:
                return d
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in seen and grid[nr][nc] in PASS:
                    seen.add((nr, nc))
                    q.append((nr, nc, d + 1))
        return -1
    bad, dists = 0, []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = go(pts[i], pts[j])
            dists.append(d)
            if d < 0:
                bad += 1
    return bad, dists


# ============================================================ 出生点
def spawns8(n=200):
    """左 4 家（偶）+ 右 4 家（奇），左右严格镜像。"""
    lx = int(n * 0.15)
    ys = [int(n * f) for f in (0.13, 0.36, 0.64, 0.87)]
    return ([(y, lx, t) for y, t in zip(ys, (0, 2, 4, 6))] +
            [(y, n - 1 - lx, t) for y, t in zip(ys, (1, 3, 5, 7))])


def spawns10(n=200):
    lx = int(n * 0.14)
    ys = [int(n * f) for f in (0.11, 0.30, 0.50, 0.70, 0.89)]
    return ([(y, lx, t) for y, t in zip(ys, (0, 2, 4, 6, 8))] +
            [(y, n - 1 - lx, t) for y, t in zip(ys, (1, 3, 5, 7, 9))])


def protect(cv, spawns, rad=14):
    """出生点禁区：禁止斑块靠近，保证出生点连通。"""
    n = cv.n
    for (sr, sc, _t) in spawns:
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                r, c = sr + dr, sc + dc
                if 0 <= r < n and 0 <= c < n:
                    cv.blk[r][c] = 1


def clear_ground(cv, spawns, rad=6):
    """出生点：只把不可通行地形降一级（高石→石、水→浅滩），绝不引入新类别。"""
    n = cv.n
    for (sr, sc, _t) in spawns:
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if dr * dr + dc * dc > rad * rad + 1:
                    continue
                r, c = sr + dr, sc + dc
                if not (0 <= r < n and 0 <= c < n):
                    continue
                t = cv.g[r][c]
                if t == HIGHSTONE:
                    cv.g[r][c] = STONE
                elif t in (WATER, SEA, OCEAN):
                    cv.g[r][c] = SHOAL


def repair(grid, max_round=80):
    """兜底：违规 2×2 整块归一到「周围 5×5 众数类」。收敛稳定，改动极小。返回 (残留, 改动格数)。"""
    H, W = len(grid), len(grid[0])
    canon = lambda t: 70 if t in WAT else t
    changed = 0
    for _ in range(max_round):
        bads = []
        for r in range(H - 1):
            for c in range(W - 1):
                ts = (grid[r][c], grid[r][c + 1], grid[r + 1][c], grid[r + 1][c + 1])
                if len({canon(t) for t in ts}) > 2:
                    bads.append((r, c))
        if not bads:
            return 0, changed
        for (r, c) in bads:
            cnt = Counter()
            for rr in range(max(0, r - 2), min(H, r + 4)):
                for cc in range(max(0, c - 2), min(W, c + 4)):
                    cnt[canon(grid[rr][cc])] += 1
            maj = cnt.most_common(1)[0][0]
            # 在邻域里找出该多数类的代表值
            val = None
            for rr in range(max(0, r - 2), min(H, r + 4)):
                for cc in range(max(0, c - 2), min(W, c + 4)):
                    if canon(grid[rr][cc]) == maj:
                        val = grid[rr][cc]
                        break
                if val is not None:
                    break
            for (y, x) in ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)):
                if canon(grid[y][x]) != maj:
                    grid[y][x] = val
                    changed += 1
    bad = 0
    for r in range(H - 1):
        for c in range(W - 1):
            ts = (grid[r][c], grid[r][c + 1], grid[r + 1][c], grid[r + 1][c + 1])
            if len({canon(t) for t in ts}) > 2:
                bad += 1
    return bad, changed


# ============================================================ 矿坑
GAP_OK = {GRASS, DIRT, STONE, SAND, MUD, SNOW, HIGHGRASS}   # 可放矿坑的地表（可通行、非水族）


def place_mines(cv, spawns, mid_nodes, per_home=2):
    """矿坑：每家 per_home 个起步 + 对称中立。要求 9×9 内无高石/水族（视觉不贴山不落水）。"""
    g, n = cv.g, cv.n
    items = [[0] * n for _ in range(n)]
    # 9×9 预判：高石或水族 → 不合格
    bad = [[0] * (n + 1) for _ in range(n + 1)]
    for r in range(n):
        for c in range(n):
            v = 1 if (g[r][c] == HIGHSTONE or g[r][c] in WAT) else 0
            bad[r + 1][c + 1] = v + bad[r][c + 1] + bad[r + 1][c] - bad[r][c]

    def ok9(r, c, rad=5):
        r0, c0, r1, c1 = r - rad, c - rad, r + rad + 1, c + rad + 1
        if r0 < 0 or c0 < 0 or r1 > n or c1 > n:
            return False
        return (bad[r1][c1] - bad[r0][c1] - bad[r1][c0] + bad[r0][c0]) == 0

    placed = []

    def far(r, c, d=5):
        return all(max(abs(r - pr), abs(c - pc)) >= d for pr, pc in placed)

    def take(r, c):
        items[r][c] = 1
        placed.append((r, c))
        if c != n - 1 - c:
            items[r][n - 1 - c] = 1
            placed.append((r, n - 1 - c))

    def find(r, c):
        if cv.inb(r, c) and g[r][c] in GAP_OK and ok9(r, c) and far(r, c):
            return r, c
        for rad in range(1, 40):
            best = None
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    if max(abs(dr), abs(dc)) != rad:
                        continue
                    rr, cc = r + dr, c + dc
                    if not cv.inb(rr, cc) or g[rr][cc] not in GAP_OK:
                        continue
                    if ok9(rr, cc) and far(rr, cc):
                        if best is None or math.hypot(dr, dc) < best[0]:
                            best = (math.hypot(dr, dc), rr, cc)
            if best:
                return best[1], best[2]
        return None

    for (sr, sc, _t) in spawns:
        if sc >= n / 2:                          # 只放左岸，右岸靠镜像生成
            continue
        side = -1 if sc < n / 2 else 1          # 朝地图内侧
        cand = [(sr - 11, sc + side * 3), (sr + 11, sc + side * 3),
                (sr, sc + side * 13), (sr - 9, sc + side * 12), (sr + 9, sc + side * 12)]
        got = 0
        for (r, c) in cand:
            if got >= per_home:
                break
            p = find(r, c)
            if p and not items[p[0]][p[1]] and far(p[0], p[1]):
                take(*p)
                got += 1

    for (r, c) in mid_nodes:
        p = find(r, c)
        if p and not items[p[0]][p[1]]:
            take(*p)
    return items


# ============================================================ 纹理变体
_VAR = [None]


def variant_map():
    if _VAR[0] is None:
        from collections import defaultdict
        root = ET.parse(C.TSX).getroot()
        sig2t, tid2sig = defaultdict(list), {}
        for t in root.findall("tile"):
            s = t.get("terrain")
            if not s:
                continue
            tid = int(t.get("id"))
            sig2t[s].append(tid)
            tid2sig[tid] = s
        _VAR[0] = (sig2t, tid2sig)
    return _VAR[0]


def tex_tid(tid, r, c, block=7):
    sig2t, tid2sig = variant_map()
    sig = tid2sig.get(tid)
    if not sig:
        return tid
    cands = sig2t[sig]
    if len(cands) <= 1:
        return tid
    h = ((r // block) * 73856093) ^ ((c // block) * 19349663) ^ 0x5bf03635
    return cands[(h & 0x7fffffff) % len(cands)]


# ============================================================ 装饰
TREE = [890, 891]
TUFT = [711, 712, 714, 898]


def make_decor(cv, rng, dens=1.7):
    g, n = cv.g, cv.n
    decor = [[0] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            t = g[r][c]
            if t == HIGHGRASS and rng.random() < 0.55 * dens:
                decor[r][c] = 1 + rng.choice(TREE)
            elif t in (GRASS, SNOW, MUD) and rng.random() < 0.075 * dens:
                decor[r][c] = 1 + rng.choice(TUFT)
    # 矿坑上不放装饰
    return decor


TREE_TILES = [9, 10, 11, 12, 13, 14]      # misc 图集里的六种树


def make_trees(cv, rng, items, spawns):
    """Items 层植树（misc tile 9~14）：林地区密植、草地稀疏点缀。

    只在「非底色」的格子上种（底色是大面积地貌，种满会变成密林封路）；
    避开矿坑 5×5、出生点 9×9、水族与悬崖。
    """
    n = cv.n
    tree = [[0] * n for _ in range(n)]
    forbid = [[0] * n for _ in range(n)]
    for (sr, sc, _t) in spawns:                       # 出生点禁区
        for dr in range(-9, 10):
            for dc in range(-9, 10):
                r, c = sr + dr, sc + dc
                if 0 <= r < n and 0 <= c < n:
                    forbid[r][c] = 1
    for r in range(n):                                # 矿坑禁区
        for c in range(n):
            if items[r][c]:
                for dr in (-3, -2, -1, 0, 1, 2, 3):
                    for dc in (-3, -2, -1, 0, 1, 2, 3):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < n and 0 <= cc < n:
                            forbid[rr][cc] = 1
    for r in range(n):
        for c in range(n):
            if forbid[r][c]:
                continue
            t = cv.g[r][c]
            if t in WAT or t == HIGHSTONE:
                continue
            p = None
            if t == HIGHGRASS and t != cv.base:
                p = 0.46                              # 林地/灌木丛：密植
            elif t == GRASS and t != cv.base:
                p = 0.14                              # 草洲/谷地：疏林
            elif t == GRASS and cv.base == GRASS:
                p = 0.022                             # 草原底色：极稀疏点缀
            elif t == SNOW:
                p = 0.055                             # 雪原：针叶疏林
            elif t == DIRT:
                p = 0.020                             # 旱地：稀疏灌木
            elif t == SAND:
                p = 0.008                             # 沙漠：极稀疏耐旱灌丛
            if p and rng.random() < p:
                tree[r][c] = MISC_FG + rng.choice(TREE_TILES)
    return tree


# ============================================================ 写出 TMX
def write_tmx(cv, decor, items, spawns, out, size=None, trees=None):
    n = cv.n if size is None else size
    g = cv.g
    # 矿坑上清装饰
    for r in range(n):
        for c in range(n):
            if items[r][c]:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < n and 0 <= cc < n:
                            decor[rr][cc] = 0
    ground_tid = C.autotile(g)
    ground = [[GROUND_FG + tex_tid(ground_tid[r][c], r, c) for c in range(n)] for r in range(n)]
    items_gid = [[0] * n for _ in range(n)]
    if trees is not None:                     # 先铺树（矿坑优先覆盖树）
        for r in range(n):
            for c in range(n):
                if trees[r][c] and not items[r][c]:
                    items_gid[r][c] = trees[r][c]
    for r in range(n):
        for c in range(n):
            if items[r][c]:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < n and 0 <= cc < n:
                            items_gid[rr][cc] = MISC_FG + ((dr + 1) * 3 + (dc + 1))
    map_el = ET.Element("map", {
        "version": "1.0", "tiledversion": "1.0.3",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(n), "height": str(n),
        "tilewidth": "20", "tileheight": "20", "nextobjectid": "1",
    })
    map_el.append(K.build_ground_tileset())

    def enc(data):
        raw = struct.pack("<%dI" % (n * n), *[data[r][c] for r in range(n) for c in range(n)])
        return base64.b64encode(gzip.compress(raw)).decode()
    for name, data in [("Ground", ground), ("Decorations", decor),
                       ("Items", items_gid), ("Units", [[0] * n for _ in range(n)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(n), "height": str(n)})
        d = ET.SubElement(l, "data", {"encoding": "base64", "compression": "gzip"})
        d.text = enc(data)
    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    nid = 1
    for (sr, sc, team) in spawns:
        o = ET.SubElement(uo, "object", {"id": str(nid), "x": str(sc * 20), "y": str(sr * 20),
                                         "width": "20", "height": "20"})
        nid += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": "commandCenter"})
    map_el.set("nextobjectid", str(nid))
    tree = ET.ElementTree(map_el)
    issues = K.validate_tmx(tree, n, n, {C.TSX: (GROUND_FG, A4.MERGED_COUNT)},
                            [(sr, sc) for sr, sc, _ in spawns])
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return issues


# ============================================================ 渲染
def render(tmx, png, scale=1):
    import numpy as np
    from PIL import Image as _Im
    root = ET.parse(tmx).getroot()
    n = int(root.get("width"))
    arr = np.array(_Im.open(C.PNG).convert("RGBA"))
    cols, TW, TH = C._COLS, 20, 20
    marr = np.array(_Im.open(os.path.join(os.path.dirname(C.PNG), "misc.png")).convert("RGBA"))
    mcols = 3

    def tile(tid):
        if tid >= 1080:                      # misc 图集（矿坑九宫格 1080..1097）
            t2 = tid - 1080
            r, c = t2 // mcols, t2 % mcols
            return marr[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :]
        r, c = tid // cols, tid % cols
        return arr[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :]
    canvas = np.zeros((n * TH, n * TW, 4), dtype=np.uint8)
    layers = {name: K._layer(root, name) for name in ("Ground", "Decorations", "Items")}
    for r in range(n):
        for c in range(n):
            y, x = r * TH, c * TW
            gv = layers["Ground"][r][c]
            if gv >= GROUND_FG:
                canvas[y:y + TH, x:x + TW] = tile(gv - GROUND_FG)
            for name in ("Decorations", "Items"):
                v = layers[name][r][c]
                if v >= GROUND_FG:
                    t = tile(v - GROUND_FG).astype(np.float32)
                    a = t[:, :, 3:4] / 255.0
                    base = canvas[y:y + TH, x:x + TW].astype(np.float32)
                    rgb = t[:, :, :3] * a + base[:, :, :3] * (1 - a)
                    al = np.maximum(base[:, :, 3:4], t[:, :, 3:4])
                    canvas[y:y + TH, x:x + TW] = np.concatenate([rgb, al], axis=2).astype(np.uint8)
    im = _Im.fromarray(canvas).convert("RGB")
    if scale != 1:
        im = im.resize((im.width * scale // 2, im.height * scale // 2), _Im.LANCZOS)
    im.save(png)
