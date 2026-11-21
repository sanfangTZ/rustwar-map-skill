# 渲染与组装管线（Rendering & Assembly Pipeline）

> 本文讲：**地形格矩阵 → gid 矩阵 → tmx 文件** 的完整转换链，以及"顶点采样"原理。

---

## 0. 总览：四段流水线

```
grid_terrain.json   ← 地形格矩阵（100×100，每格 1 个地形值）
        │  gen_gids.py（顶点采样渲染）
        ▼
gids_terrain.json   ← gid 矩阵（100×100，每格 1 个图集编号）
        │  make_final.py（组装 tmx）
        ▼
X.tmx               ← 最终地图文件
        │  verify + preview（校验 + 验收图）
        ▼
部署到 maps 目录
```

**每一步都能单独跑、单独看结果**，出错能立刻定位在哪一段。

---

## 1. 顶点采样原理（最重要）

### 图集是什么
`地面层整合.png` 是一张**图集（atlas）**，横向 `COLS=36` 列，每格 `TS = 宽/36` 像素。
每个 gid 对应图集里的一个 tile：
```python
def tile(gid, ts):
    tid = gid - 1
    c = tid % COLS; r = tid // COLS
    return atlas.crop((c*TS, r*TS, (c+1)*TS, (r+1)*TS)).resize((ts, ts))
```

### 一个 tile 怎么决定用哪个 gid？
铁锈战争的 Ground 层是**顶点模型**：
- 地图有 `(W+1)×(H+1)` 个**顶点**网格；
- 每个 tile 的四角，各由一个**顶点地形**决定；
- **顶点地形 = 该顶点周围 2×2 个格子地形的"多数投票"**，平票取**较小值**。

```python
def sample(terr, vx, vy, W, H):
    """取顶点 (vx,vy) 周围 2x2 格做多数投票"""
    cells = []
    for dy in (-1, 0):
        for dx in (-1, 0):
            x, y = vx+dx, vy+dy
            if 0 <= x < W and 0 <= y < H:
                cells.append(terr[y][x])
    if not cells:
        return 0
    cnt = Counter(cells)
    best = max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))   # 票多优先; 平票取小
    return best[0]
```

### 关键推论
1. **孤立单格会被抹平**：单格高石 14 在 3 个石 2 的 2×2 窗口里只有 1/4 票 → 被投成石 2 → 不可见。
2. **成片 ≥ 2×2 才可见**：2×2 高石簇让簇内顶点拿到 ≥ 2/4 票 → 稳定渲染。
3. **对角组合缺失**：图集没有 `(a,b,b,a)` / `(b,a,a,b)` 这类"对角鞍点"，全局无法避免（只要保证四邻 ≤ 2 种，这种组合就不出现）。

---

## 2. gen_gids.py（渲染器）核心

```python
import json, collections
from collections import Counter

terr = json.load(open('grid_terrain.json'))
W, H = len(terr[0]), len(terr)

# 1) 动态建"合法 quad → gid"查询表（从图集字典反向索引）
#    ground_dict.json：names(地形名列表) + tiles(gid → {terrain:[4角], props:[]})
D = json.load(open('ground_dict.json'))
comb = {}   # (tl,tr,bl,br) -> [gid,...]
for gid_s, v in D['tiles'].items():
    t = v.get('terrain') if isinstance(v, dict) else v
    if t and len(t) == 4:
        comb.setdefault(tuple(t), []).append(int(gid_s))

# 2) 逐 tile 顶点采样 → 拼四角 → 查表
out = [[0]*W for _ in range(H)]
miss = fuzzy = 0
for y in range(H):
    for x in range(W):
        tl = sample(terr, x,   y,   W, H)
        tr = sample(terr, x+1, y,   W, H)
        bl = sample(terr, x,   y+1, W, H)
        br = sample(terr, x+1, y+1, W, H)
        key = (tl, tr, bl, br)
        if key in comb:
            out[y][x] = comb[key][0]
        else:
            # 模糊回退：在已知 quad 里找汉明距离最小的
            miss += 1
            best, bd = None, 9
            for k, gs in comb.items():
                d = sum(1 for a, b in zip(k, key) if a != b)
                if d < bd:
                    bd, best = d, gs[0]
            out[y][x] = best
            fuzzy += 1

json.dump(out, open('gids_terrain.json', 'w'))
print('精确:', W*H - miss, ' 模糊回退:', fuzzy)
```

> **判定成功的标准**：`精确 = 10000，模糊回退 = 0`。
> 若模糊回退 > 0，说明布局有"四邻 > 2 种"的违规格，回去改布局。

---

## 3. make_final.py（组装 tmx）核心

```python
import re, json, gzip, base64, struct

MAPS = '/sdcard/Download/QQ/rustedWarfare/maps'
SRC  = MAPS + '/★模板.tmx'
OUT  = MAPS + '/★新图★.tmx'
W = H = 100
gids = json.load(open('gids_terrain.json'))

def make_data(arr):
    flat = [g for row in arr for g in row]
    raw = struct.pack('<%dI' % len(flat), *flat)
    comp = gzip.compress(raw, mtime=0)
    return base64.b64encode(comp).decode('ascii')

src = open(SRC, encoding='utf-8').read()
# 1) 尺寸
out = re.sub(r'(?<!tile)width="\d+"',  'width="%d"'  % W, src)
out = re.sub(r'(?<!tile)height="\d+"', 'height="%d"' % H, out)
# 2) Ground 层（base64+gzip 的 uint32 数组）
new_ground = '<layer name="Ground" width="%d" height="%d"><data encoding="base64" compression="gzip">%s</data></layer>' % (W, H, make_data(gids))
out = re.sub(r'<layer name="Ground".*?</layer>', lambda m: new_ground, out, count=1, flags=re.S)
# 3) Items / Units 层全 0
# 4) 出生点 commandCenter（四角，team 0/1/2/3）
# 5) Triggers 里的 map_info（type=skirmish + introText）
open(OUT, 'w', encoding='utf-8').write(out)
```

- **模板必须用一张"尺寸接近"的干净图**（如修边测试版），避免残留物件。
- **introText 里写清要素**，方便游戏里一眼识别。
- **出生点像素坐标 = 格号 × 20**（gid 每格 20px），`commandCenter` 宽高 20×20。

---

## 4. verify + preview（验收）

### 4.1 地形三重校验（`verify_terrain.py`）
```bash
python3 verify_terrain.py <tmx> <grid.json>
```
输出：XML 合法性 / Ground 格数 / gid 范围 / 出生点 3×3 纯草 / 四角地形组合种类。

### 4.2 渲染验收图（`preview.py`）
- **整体缩略**：每格 6px，看宏观构图。
- **局部放大**：山体 / 悬崖 / 岩浆特写，`Image.NEAREST` 放大 40~60 倍。
- 全部**从最终 tmx 的 Ground 层 gid 直接渲染**（不是从 grid！），保证"所见即所得"。

```python
# 放大一个区间的通用函数
def crop_zoom(X0, Y0, X1, Y1, Z, name):
    cw, ch = (X1-X0)*TS, (Y1-Y0)*TS
    crop = Image.new('RGBA', (cw, ch), (30,30,30,255))
    for y in range(Y0, Y1):
        for x in range(X0, X1):
            crop.paste(tile(g[y][x]), ((x-X0)*TS, (y-Y0)*TS))
    crop.resize((cw*Z//TS, ch*Z//TS), Image.NEAREST).convert('RGB').save(BASE+'/'+name)
```

---

## 5. 完整命令链（可照抄）

```bash
set +e
cd <工作目录>
python3 build_terrain.py        # 生成 grid_terrain.json（布局）
python3 gen_gids.py             # grid → gids（渲染，须精确 10000/0）
python3 check_gids.py           # 独立交叉验证（2×2 顶点 >2 种 = 0）
python3 make_final.py           # 组装 tmx
python3 verify_terrain.py '<tmx>' grid_terrain.json   # 终检
python3 preview.py              # 出验收图
cp '<tmx>' <maps目录>/          # 部署
```

---

## 6. 常见渲染问题速查

| 症状 | 原因 | 解法 |
|---|---|---|
| 某地形看不见 | 孤立单格被采样抹平 | 改 2×2 成片（§4） |
| 模糊回退 > 0 | 布局有 3 色同现格 | 加隔离带，或跑迭代修复器 |
| 图里出现花块 | 命中缺失的对角鞍点 | 全局保证四邻 ≤ 2 种 |
| gid 超范围 | 用错图集字典 | 用本图的 `ground_dict.json` |
| Ground 层错位 | uint32 字节序 | 必须 `<I`（小端 4 字节） |

---

> 署名：三方同志｜作者交流 QQ 群：528400691