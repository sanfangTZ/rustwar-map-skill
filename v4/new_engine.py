# -*- coding: utf-8 -*-
"""八张 120×120 竞速图 · 原版向重制引擎

从两张官方图（Two Sides / Bridges Over Lava, 均 120×120）逆推出的硬规则：
  1) 屏障（岩浆/水/山脉）用自然轮廓，绝不出现正圆、同心环、等距放射线；
  2) 跨屏障的通道 = 石地（Stone），不是浅滩。官方桥 = 石桥面 6 格 + 石↔岩浆过渡带；
  3) 浅滩只做水边的自然过渡，绝不当桥用（对方口中的"假水"）；
  4) 矿坑 = misc 3×3 九宫格，12 个 / 120×120，中心对称散布、少量成对；
  5) 树是点缀：官方 9 棵，我们 20~30 棵，成片不长满。

过渡约束（图集实测，任何 2×2 最多 2 类）：
  岩浆(11) 只能接 土(1)/石(2)；高石(14) 只能接 草(0)/石(2)；
  雪(5) 接 草/土/石/泥；高草(12) 接 草/泥/水。
"""
import os, sys, math, random, struct, base64, gzip
import xml.etree.ElementTree as ET
from collections import Counter, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_combined as C
import gen_koth as K
import gen_4v4_arena as A4

GRASS, DIRT, STONE, SAND, MUD = 0, 1, 2, 3, 4
SNOW, LAVA = 5, 11
SHOAL, WATER, SEA, OCEAN = 23, 7, 8, 9
HIGHGRASS, HIGHSTONE = 12, 14

WAT = {WATER, SEA, OCEAN, SHOAL}
BLOCK = {LAVA, HIGHSTONE, WATER, SEA, OCEAN}      # 不可通行
PASS = {GRASS, DIRT, STONE, SAND, MUD, SNOW, HIGHGRASS, SHOAL}
NM = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 5: "雪", 7: "水", 8: "海",
      9: "洋", 11: "岩浆", 12: "高草", 14: "高石", 23: "浅滩"}


# ============================================================ 噪声
def fbm(r, c, seed, f=0.045, oct_=3):
    """多频正弦叠加 → 有机起伏（无周期感）。"""
    v, amp, fr = 0.0, 1.0, f
    for i in range(oct_):
        v += amp * (math.sin(r * fr + seed * 1.7 + i * 2.1) *
                    math.cos(c * fr * 1.13 - seed * 0.9 + i * 1.3))
        amp *= 0.52
        fr *= 2.07
    return v


def n1(t, seed, f, amp):
    return amp * (math.sin(t * f + seed) * 0.62 + math.sin(t * f * 2.31 + seed * 1.71) * 0.38)


# ============================================================ 画布
class CV:
    def __init__(self, n, base=GRASS):
        self.n = n
        self.base = base
        self.g = [[base] * n for _ in range(n)]
        self.used = [[0] * n for _ in range(n)]

    def inb(self, r, c):
        return 0 <= r < self.n and 0 <= c < self.n

    def put(self, r, c, cat):
        if 0 <= r < self.n and 0 <= c < self.n:
            self.g[r][c] = cat

    # ---------- 屏障：笔刷沿路径刷出连续带（不断裂、边缘圆滑） ----------
    def strip(self, path, half, cat, edge=None, edge_w=0, jitter=0.0, seed=0.0):
        n = self.n
        dense = []
        for i in range(len(path) - 1):
            (r0, c0), (r1, c1) = path[i], path[i + 1]
            steps = max(1, int(max(abs(r1 - r0), abs(c1 - c0)) * 2))
            for s in range(steps):
                t = s / steps
                dense.append((r0 + (r1 - r0) * t, c0 + (c1 - c0) * t))
        dense.append(path[-1])
        reach = half + (edge_w if edge else 0)
        for (r, c) in dense:
            hw = half + (jitter * fbm(r, c, seed) if jitter else 0)
            rr0, rr1 = int(r - reach - 1), int(r + reach + 2)
            cc0, cc1 = int(c - reach - 1), int(c + reach + 2)
            for rr in range(max(0, rr0), min(n, rr1)):
                for cc in range(max(0, cc0), min(n, cc1)):
                    d = math.hypot(rr - r, cc - c)
                    if d <= hw:
                        self.g[rr][cc] = cat
                    elif edge is not None and d <= hw + edge_w:
                        if self.g[rr][cc] != cat:
                            self.g[rr][cc] = edge

    def bridge(self, r0, r1, c0, c1, cat=STONE, rough=0.0, seed=0.0):
        """桥：沿通行方向窄、跨屏障方向宽；rough>0 时桥缘带自然锯齿。"""
        for r in range(int(r0), int(r1) + 1):
            for c in range(int(c0), int(c1) + 1):
                if rough:
                    edge = (r == int(r0) or r == int(r1) or c == int(c0) or c == int(c1))
                    if edge and fbm(r, c, seed, 0.22, 2) > rough:
                        continue
                self.put(r, c, cat)

    # ---------- 不规则斑块（湖/林/丘） ----------
    def blob(self, cy, cx, rad, cat, rng, lobes=7, jit=0.30, squash=1.0, only=None, gap=0):
        n = self.n
        ph = [rng.uniform(0, math.tau) for _ in range(lobes)]
        amp = [rng.uniform(0.6, 1.3) for _ in range(lobes)]
        # ★ 第二谐波：同频率叠加在数学上是"完美 N 瓣玫瑰花线"（齿轮感/AI味根源），
        #   加一个 2N+1 次小谐波打破均匀瓣距 → 自然有机轮廓。
        h2p = rng.uniform(0, math.tau)
        h2f = lobes * 2 + 1
        cells = []
        R = rad * 1.45 + 2
        for r in range(max(0, int(cy - R * squash - 1)), min(n, int(cy + R * squash + 2))):
            for c in range(max(0, int(cx - R - 1)), min(n, int(cx + R + 2))):
                if gap and self.used[r][c]:
                    continue
                if only is not None and self.g[r][c] not in only:
                    continue
                dy, dx = (r - cy) / squash, c - cx
                d = math.hypot(dy, dx)
                a = math.atan2(dy, dx)
                k = sum(amp[i] * math.cos(lobes * a + ph[i]) for i in range(lobes)) / lobes \
                    + 0.38 * math.cos(h2f * a + h2p)
                if d <= rad * (1 + jit * k):
                    self.g[r][c] = cat
                    cells.append((r, c))
        if gap:
            for (r, c) in cells:
                for dr in range(-gap, gap + 1):
                    for dc in range(-gap, gap + 1):
                        if 0 <= r + dr < n and 0 <= c + dc < n:
                            self.used[r + dr][c + dc] = 1
        return cells

    def disc(self, cy, cx, rad, cat, only=None):
        cells = []
        for r in range(max(0, int(cy - rad - 1)), min(self.n, int(cy + rad + 2))):
            for c in range(max(0, int(cx - rad - 1)), min(self.n, int(cx + rad + 2))):
                if only is not None and self.g[r][c] not in only:
                    continue
                if (r - cy) ** 2 + (c - cx) ** 2 <= rad * rad:
                    self.g[r][c] = cat
                    cells.append((r, c))
        return cells

    def count(self):
        return Counter(v for row in self.g for v in row)


# ============================================================ 校验
def nf(grid):
    return C.verify_no_flower(grid)


def edge_rate(grid):
    return C.edge_pass_rate(grid)


def repair(grid, rounds=60):
    """只对违规 2×2 做块内归一到邻域众数（收敛稳定）。"""
    H, W = len(grid), len(grid[0])
    canon = lambda t: 70 if t in WAT else t
    changed = 0
    for _ in range(rounds):
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
    bad = sum(1 for r in range(H - 1) for c in range(W - 1)
              if len({canon(grid[r][c]), canon(grid[r][c + 1]),
                      canon(grid[r + 1][c]), canon(grid[r + 1][c + 1])}) > 2)
    return bad, changed


def bfs_ok(grid, spawns):
    H, W = len(grid), len(grid[0])
    pts = [(r, c) for r, c, _ in spawns]

    def go(s, t):
        if grid[s[0]][s[1]] not in PASS or grid[t[0]][t[1]] not in PASS:
            return -1
        seen, q = {s}, deque([(s[0], s[1], 0)])
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
    bad = 0
    dists = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = go(pts[i], pts[j])
            dists.append(d)
            if d < 0:
                bad += 1
    return bad, dists


def connect_all(cv, spawns, width=2):
    """兜底连通：用最小破坏代价路径（Dijkstra）打通所有出生点。

    代价：可通行=1，石=1，悬崖/岩浆/深水=60。沿最省路径把屏障降为石（3 格宽），
    只在必须处开洞，不破坏整体设计。
    """
    import heapq
    n = cv.n
    g = cv.g

    def cost(t):
        if t in PASS:
            return 1
        if t == STONE:
            return 1
        return 60

    def path(a, b):
        dist = [[float("inf")] * n for _ in range(n)]
        prev = [[None] * n for _ in range(n)]
        sr, sc = a
        dist[sr][sc] = 0
        pq = [(0, sr, sc)]
        while pq:
            d, r, c = heapq.heappop(pq)
            if d > dist[r][c]:
                continue
            if (r, c) == b:
                break
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < n and 0 <= nc < n):
                    continue
                nd = d + cost(g[nr][nc])
                if nd < dist[nr][nc]:
                    dist[nr][nc] = nd
                    prev[nr][nc] = (r, c)
                    heapq.heappush(pq, (nd, nr, nc))
        if dist[b[0]][b[1]] == float("inf"):
            return None
        out, cur = [], b
        while cur:
            out.append(cur)
            cur = prev[cur[0]][cur[1]]
        return out[::-1]

    pts = [(r, c) for r, c, _ in spawns]
    changed = 0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            p = path(pts[i], pts[j])
            if not p:
                continue
            for (r, c) in p:
                if g[r][c] in BLOCK:
                    for dr in range(-width, width + 1):
                        for dc in range(-width, width + 1):
                            rr, cc = r + dr, c + dc
                            if 0 <= rr < n and 0 <= cc < n and g[rr][cc] in BLOCK:
                                g[rr][cc] = STONE
                                changed += 1
    return changed


# ============================================================ 出生点
def spawns_corners(n, per_corner=2):
    """四角各 per_corner 家（8 家）。"""
    m = n * 0.17
    corners = [(m, m), (m, n - 1 - m), (n - 1 - m, m), (n - 1 - m, n - 1 - m)]
    out = []
    t = 0
    for ci, (cr, cc) in enumerate(corners):
        for k in range(per_corner):
            off = (k - (per_corner - 1) / 2) * (n * 0.13)
            if ci in (0, 3):
                out.append((int(cr + off), int(cc), t))
            else:
                out.append((int(cr - off), int(cc), t))
            t += 1
    return out


def spawns_sides(n, per_side=4):
    """左右各 per_side 家。"""
    lx = int(n * 0.13)
    ys = [int(n * f) for f in (0.16, 0.39, 0.61, 0.84)]
    return ([(y, lx, i * 2) for i, y in enumerate(ys)] +
            [(y, n - 1 - lx, i * 2 + 1) for i, y in enumerate(ys)])


def spawns_quad(n):
    """四边各 2 家（上下左右），共 8 家。"""
    m = int(n * 0.16)
    mid = n // 2
    d = int(n * 0.14)
    return [(m, mid - d, 0), (m, mid + d, 1),
            (n - 1 - m, mid - d, 2), (n - 1 - m, mid + d, 3),
            (mid - d, m, 4), (mid + d, m, 5),
            (mid - d, n - 1 - m, 6), (mid + d, n - 1 - m, 7)]


def spawns10(n):
    lx = int(n * 0.12)
    ys = [int(n * f) for f in (0.10, 0.30, 0.50, 0.70, 0.90)]
    return ([(y, lx, i * 2) for i, y in enumerate(ys)] +
            [(y, n - 1 - lx, i * 2 + 1) for i, y in enumerate(ys)])


# ============================================================ 矿坑（官方模式）
def place_mines(cv, spawns, count, rng):
    """12 个 3×3 矿坑：中心对称散布，多数单点、少量成对；避开屏障与出生点。"""
    n = cv.n
    items = [[0] * n for _ in range(n)]

    def ok(r, c, rad=3):
        if not (rad <= r < n - rad and rad <= c < n - rad):
            return False
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if cv.g[r + dr][c + dc] in BLOCK:
                    return False
        return True

    for (sr, sc, _t) in spawns:
        for dr in range(-5, 6):
            for dc in range(-5, 6):
                if cv.inb(sr + dr, sc + dc):
                    items[sr + dr][sc + dc] = -1      # 占位：出生点区不布矿

    half = count // 2
    placed = []
    tries = 0
    while len(placed) < half and tries < 20000:
        tries += 1
        r = rng.randint(10, n - 11)
        c = rng.randint(10, n - 11)
        mr, mc = n - 1 - r, n - 1 - c
        if not ok(r, c) or not ok(mr, mc):
            continue
        if items[r][c] or items[mr][mc]:
            continue
        if any(max(abs(r - pr), abs(c - pc)) < 8 for pr, pc in placed):
            continue
        items[r][c] = 1
        items[mr][mc] = 1
        placed += [(r, c), (mr, mc)]
        # 30% 概率加一个"成对"矿（相距 7~9 格）
        if rng.random() < 0.30 and len(placed) < count:
            d = rng.randint(7, 9)
            dr, dc = (0, d) if rng.random() < 0.5 else (d, 0)
            r2, c2 = r + dr, c + dc
            m2r, m2c = n - 1 - r2, n - 1 - c2
            if ok(r2, c2) and ok(m2r, m2c) and not items[r2][c2] and not items[m2r][m2c]:
                items[r2][c2] = 1
                items[m2r][m2c] = 1
                placed += [(r2, c2), (m2r, m2c)]
    # 不足目标数 → 单点补齐（官方图也不是严格逐点对称，允许少量浮动）
    got = sum(1 for r in range(n) for c in range(n) if items[r][c] == 1)
    tries2 = 0
    while got < count and tries2 < 30000:
        tries2 += 1
        r = rng.randint(9, n - 10)
        c = rng.randint(9, n - 10)
        if items[r][c] or not ok(r, c):
            continue
        if any(max(abs(r - pr), abs(c - pc)) < 7 for pr, pc in placed):
            continue
        items[r][c] = 1
        placed.append((r, c))
        got += 1
    for r in range(n):
        for c in range(n):
            if items[r][c] < 0:
                items[r][c] = 0
    return items


# ============================================================ 树种
def place_trees(cv, spawns, items, rng, count=26):
    """Items 层植树：成片点缀，避开矿坑/出生点/屏障。"""
    n = cv.n
    tree = [[0] * n for _ in range(n)]
    forb = [[0] * n for _ in range(n)]
    for (sr, sc, _t) in spawns:
        for dr in range(-7, 8):
            for dc in range(-7, 8):
                if cv.inb(sr + dr, sc + dc):
                    forb[sr + dr][sc + dc] = 1
    for r in range(n):
        for c in range(n):
            if items[r][c]:
                for dr in range(-3, 4):
                    for dc in range(-3, 4):
                        if cv.inb(r + dr, c + dc):
                            forb[r + dr][c + dc] = 1
    cand = [(r, c) for r in range(3, n - 3) for c in range(3, n - 3)
            if not forb[r][c] and cv.g[r][c] in (GRASS, SNOW, DIRT, HIGHGRASS)]
    rng.shuffle(cand)
    got = 0
    for (r, c) in cand:
        if got >= count:
            break
        if any(tree[r + dr][c + dc] for dr in range(-2, 3) for dc in range(-2, 3)
               if cv.inb(r + dr, c + dc)):
            continue
        tree[r][c] = 1090 + rng.randrange(6)
        got += 1
    return tree, got


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


def tex_tid(tid, r, c, block=6):
    sig2t, tid2sig = variant_map()
    sig = tid2sig.get(tid)
    if not sig:
        return tid
    cands = sig2t[sig]
    if len(cands) <= 1:
        return tid
    h = ((r // block) * 73856093) ^ ((c // block) * 19349663) ^ 0x5bf03635
    return cands[(h & 0x7fffffff) % len(cands)]


# ============================================================ 写出
GROUND_FG, MISC_FG = A4.GROUND_FG, A4.MISC_FG


def write_tmx(cv, items, trees, spawns, out):
    n = cv.n
    g = cv.g
    gtid = C.autotile(g)
    ground = [[GROUND_FG + tex_tid(gtid[r][c], r, c) for c in range(n)] for r in range(n)]
    items_gid = [[0] * n for _ in range(n)]
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
    for name, data in [("Ground", ground), ("Decorations", [[0] * n for _ in range(n)]),
                       ("Items", items_gid), ("Units", [[0] * n for _ in range(n)])]:
        l = ET.SubElement(map_el, "layer", {"name": name, "width": str(n), "height": str(n)})
        d = ET.SubElement(l, "data", {"encoding": "base64", "compression": "gzip"})
        d.text = enc(data)
    uo = ET.SubElement(map_el, "objectgroup", {"name": "UnitObjects"})
    oid = 1
    for (sr, sc, team) in spawns:
        o = ET.SubElement(uo, "object", {"id": str(oid), "x": str(sc * 20), "y": str(sr * 20),
                                         "width": "20", "height": "20"})
        oid += 1
        p = ET.SubElement(o, "properties")
        ET.SubElement(p, "property", {"name": "team", "value": str(team)})
        ET.SubElement(p, "property", {"name": "unit", "value": "commandCenter"})
    # 官方 skirmish 图标准配置：Triggers 组 + map_info(type=skirmish)
    tg = ET.SubElement(map_el, "objectgroup", {"name": "Triggers"})
    o = ET.SubElement(tg, "object", {"id": str(oid), "name": "map_info",
                                     "x": "40", "y": "41", "width": "203", "height": "122"})
    oid += 1
    pp = ET.SubElement(o, "properties")
    ET.SubElement(pp, "property", {"name": "type", "value": "skirmish"})
    map_el.set("nextobjectid", str(oid))
    tree = ET.ElementTree(map_el)
    issues = K.validate_tmx(tree, n, n, {C.TSX: (GROUND_FG, A4.MERGED_COUNT)},
                            [(r, c) for r, c, _ in spawns])
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return issues


# ============================================================ 渲染
def render(tmx, png, scale=2):
    import numpy as np
    from PIL import Image as _Im
    root = ET.parse(tmx).getroot()
    n = int(root.get("width"))
    arr = np.array(_Im.open(C.PNG).convert("RGBA"))
    cols, TW, TH = C._COLS, 20, 20
    marr = np.array(_Im.open(os.path.join(os.path.dirname(C.PNG), "misc.png")).convert("RGBA"))
    mcols = 3

    def tile(tid):
        if tid >= 1080:
            t2 = tid - 1080
            r, c = t2 // mcols, t2 % mcols
            return marr[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :]
        r, c = tid // cols, tid % cols
        return arr[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW, :]
    canvas = np.zeros((n * TH, n * TW, 4), dtype=np.uint8)
    layers = {name: K._layer(root, name) for name in ("Ground", "Items")}
    for r in range(n):
        for c in range(n):
            y, x = r * TH, c * TW
            gv = layers["Ground"][r][c]
            if gv >= GROUND_FG:
                canvas[y:y + TH, x:x + TW] = tile(gv - GROUND_FG)
            v = layers["Items"][r][c]
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
