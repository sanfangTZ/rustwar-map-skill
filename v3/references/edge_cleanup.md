# 修边与视觉质量专项（Edge Cleanup & Visual Quality）

> 铁锈战争地图**地形做厚了是基础，修边干净才是验收**。用户反复骂的就是"修边没整好"。
> 本文件把修边相关的所有坑、以及"改了却完全没生效"的隐藏 bug 全部固化。
> 配套：`competitive_4v4.md`（4V4 范式）、`terrain_compat.md`（兼容矩阵）、`terrain_generation.md`（方法论）。

---

## ★ A. 最阴险的坑：cleanup 函数"改了却完全没生效"

**症状**：你写了一个 `cleanup(grid)` 想修边，跑完地形却和没修一模一样；孤立尖刺数、对角伪影数前后完全一致。

**根因（真实踩过）**：

```python
def cleanup(grid):
    ...
    for _ in range(2):
        nxt = [row[:] for row in grid]     # 复制一份
        for ...: nxt[r][c] = dom            # 改的是 nxt
        grid = [row[:] for row in nxt]      # ❌ 只重新绑定了局部变量 grid
    return grid                            # 调用处却丢弃返回值 → 原 grid 一行没动
```

`grid = [...]` 只是把**函数内的局部变量名**重新指向新列表；**调用处**拿到的还是原来的旧引用（或根本没接返回值）。结果：函数在"自言自语"，地图纹丝不动。

**正确写法 —— 原地修改，先收集后统一应用**（避免同轮读脏）：

```python
def cleanup(grid):
    H = len(grid); W = len(grid[0])
    ORTH = ((1,0),(-1,0),(0,1),(0,-1))
    DIAG = ((1,1),(1,-1),(-1,1),(-1,-1))
    for _ in range(2):
        changes = []                       # ① 先收集所有变更
        for r in range(1, H-1):
            for c in range(1, W-1):
                cat = grid[r][c]
                if cat not in PAINT: continue
                orth = [grid[r+dr][c+dc] for dr,dc in ORTH]
                diag = [grid[r+dr][c+dc] for dr,dc in DIAG]
                cnt  = sum(1 for x in orth+diag if x == cat)
                if cnt < 3:
                    dom = Counter(orth+diag).most_common(1)[0][0]
                    if dom in PAINT: changes.append((r,c,dom))
                elif cat not in orth and any(x==cat for x in diag):
                    co = Counter(x for x in orth if x in PAINT)
                    if co: changes.append((r,c,co.most_common(1)[0][0]))
        for (r,c,v) in changes:
            grid[r][c] = v                 # ② 统一原地写入
    return grid                            # 返回原引用即可（已原地改）
```

> **铁律**：修改二维列表/numpy 数组的函数，**要么原地改并返回原引用，要么调用处必须 `grid = cleanup(grid)` 接返回值**。不要两者都做一半。
> **验证招数**：写个"清理前后指标对比"脚本（见 §J），前后数字一样就说明函数没生效——这招能在不看图的情况下立刻抓出这个 bug。

---

## B. 元胞平滑 → 45° 锯齿楼梯

**症状**：用 `n<=3 删、n>=5 补` 的元胞自动机平滑泥/水边缘，必然长出**45° 阶梯状锯齿**（和海岸平滑曲线一对比格外扎眼）。

**根因**：元胞自动机的离散阈值本质就是产生曼哈顿/斜向台阶，高频细节越多越碎。

**正解**：**高斯模糊 + 重阈值**（分离卷积，5-tap `[1,4,6,4,1]/16`，横竖各 2 次）得到圆滑有机轮廓：

```python
m = np.array(f, dtype=np.float64)
_k = np.array([1.,4.,6.,4.,1.]) / 16.
def _gblur(a, axis):
    pads = [(0,0),(0,0)]; pads[axis] = (2,2)
    ap = np.pad(a, pads, mode="edge")
    sl = [slice(None), slice(None)]; out = np.zeros_like(a)
    for i in range(5):
        sl[axis] = slice(i, i+a.shape[axis]); out += _k[i]*ap[tuple(sl)]
    return out
for _ in range(2):
    m = _gblur(m, 0); m = _gblur(m, 1)
f = [[int(v) for v in row] for row in (m > 0.46)]   # 重阈值
```

---

## C. 高频噪声掐碎连续地形（山脊变虚线段）

**症状**：山体/山脊脊线上叠了高频噪声 → 山体被绞成**一节节虚线段**（断成 5~6 截，满山碎点）。

**正解**：脊线只用**低频缓弯** + 连续距离场，半宽缓变（中心必有纯高石块）：

```python
def ridge(c0):
    for r in range(10, SIZE-10):
        spine = c0 + 3.5*math.sin(r*0.055) + 3.0*_noise(r, c0)   # 低频缓弯
        half  = 3.0 + 0.8*math.sin(r*0.023 + c0)                  # 半宽 2.2~3.8 缓变
        for c in range(int(spine-half)-2, int(spine+half)+3):
            if abs(c - spine) <= half + 0.4*_noise(r, c+500):     # 连续函数边界
                if 0 <= c < W and grid[r][c] in (GRASS, DIRT, MUD, HIGHGRASS, SAND):
                    grid[r][c] = HIGHSTONE
```

> 顶点边界是连续函数（相邻行变化 <0.1 格）→ 过渡只是一圈干净边缘块，不会碎。

---

## D. 曼哈顿菱形洞 → 圆形洞

**症状**：出生点/资源避让用曼哈顿距离 `abs(dr)+abs(dc) < R` → 切出**完美 45° 菱形**避让区，机械生硬。

**正解**：欧氏距离 `dr*dr + dc*dc < R*R` → 圆形洞：

```python
if any((r-sr)**2 + (c-sc)**2 < R*R for sr,sc,_t in spawns):
    continue   # 圆形避让，柔和自然
```

> 注意半径别太大：半径 11（洞径 22）会横穿 27 格宽的资源带，把盆地拦腰切断成多片；
> 半径 7 仍有安全缓冲，且能让盆地从洞两侧绕过去保持完整。

---

## E. 中频噪声泥块撕裂（轮廓碎裂 + 多片）

**症状**：泥盆用中高频噪声 → 边缘碎波浪、**被出生点洞拦腰切断成 2~3 块撕裂状**。

**正解**：低频长波噪声（轮廓波长 40~80 格，平滑大曲线）+ 高斯模糊（§B）+ **每侧只留最大连通片**：

```python
if 0.65*_vn(r+3000, c+3000, 1/42.0) + 0.35*_vn(r+3000, c+3000, 1/21.0) > 0.02:
    f[r][c] = 1     # 低频长波：中高频会让边缘碎
```

> **顺序坑（见 §I）**：模糊重阈值**必须放在**"只留最大连通片"过滤**之前**。
> 若先过滤后模糊，模糊重阈值会再次把已过滤的大片碎裂。

---

## F. 边界笔直竖线 → 低频噪声波浪边

**症状**：资源带/荒漠带用常数半宽 `cols ∈ [CENTER±HALF]` → **笔直竖线**，太机械。

**正解**：边界逐行用低频噪声摆动（叠一个更快 octave 增加细节），形成有机波浪边：

```python
edge = DESERT_HALF + 7.0*_vn(r*0.35, 77.0, 1/28.0) + 3.0*_vn(r*0.35, 155.0, 1/12.0)
if abs(c - CENTER) < edge:     # 波浪形边界，而非直线
    ...
```

---

## G. "仅对角相连"的 autotile 伪影

**症状**：某格的正交四邻**没有同类**，但**对角有同类** → autotile 四角在角点接触，渲染出杂色角点（棋盘/白点）。这是"修边没修好"最常见的根因之一。

**正解**：`cleanup()` ② 打断这种连接 —— 当正交邻无同类、对角有同类时，把该格拉成"占多数正交邻"的类别，**强制 4-连通**（见 §A 代码 `elif cat not in orth and any(...)` 分支）。

---

## H. 装饰污染（高石上撒红棕岩石）

**症状**：山脊/高石上撒了 GID `827`（红棕岩石，RGB[129,105,96]）→ 灰色石山（RGB[83,83,83]）变成**满山红砖杂斑**，用户骂"黑色石头一大坨乱七八糟"。

**根因**：827 是为草地/泥地设计的红棕岩石，与灰石不搭。

**正解**：
- **高石（HIGHSTONE）禁止撒任何装饰** —— 它自身已有完整石纹。
- 岩石装饰（`GID = 1+826 = 827`）只撒在 **STONE/石地**；枯木（`GID = 1+934 = 935`）只撒在 **MUD/泥地**（同色系、成簇）：

```python
def make_decor(grid, rng):
    decor = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == MUD and _noise(r+8000, c-8000) > 0.5:
                decor[r][c] = 1 + 934      # 枯木（泥地专属）
    return decor
    # 高石：什么都不撒
```

---

## I. 连通片过滤顺序（先模糊、后过滤）

**原则**：`模糊重阈值`（§B）会产生新的小碎片，因此必须放在 `只留最大连通片` 过滤**之前**：

```
mask生成 → 高斯模糊+重阈值(可能碎裂) → 删掉 ≤N 格的小连通片 → 写回 grid
```

若反过来（先过滤掉小片、再模糊），模糊会把已清理的大片**重新碎裂成小片**，等于白做。
过滤用 4-邻域 flood fill，按侧（中轴左/右）各取最大片即可。

---

## J. 环境无图兜底：用"定量指标 + 结构校验"代替肉眼

> **重要实情**：生成地图的沙盒环境**可能屏蔽 PNG 读入**（图片无法被肉眼/多模态读取）。
> **本 Skill 的设计前提是：AI 完全不需要看渲染图也能保证质量。** 下面的量化手段是**默认主路径**（不依赖任何看图能力），截图放大（J.3）只是"环境恰好能读图时"的可选增强——**绝不能把它当成必需步骤**，更不要假装看到了图。最后成品一律请用户肉眼过目。

### J.1 连通片统计（定位碎片/撕裂）
```python
def components(grid, cat):
    H=W=len(grid); seen=[[0]*W for _ in range(H)]; out=[]
    for r in range(H):
        for c in range(W):
            if grid[r][c]==cat and not seen[r][c]:
                st=[(r,c)]; seen[r][c]=1; cells=[]
                while st:
                    rr,cc=st.pop(); cells.append((rr,cc))
                    for dr,dc in((1,0),(-1,0),(0,1),(0,-1)):
                        a,b=rr+dr,cc+dc
                        if 0<=a<H and 0<=b<W and grid[a][b]==cat and not seen[a][b]:
                            seen[a][b]=1; st.append((a,b))
                out.append(cells)
    return out
# 用法：sizes = sorted(len(x) for x in components(grid, MUD), reverse=True)
#       小碎片 = [s for s in sizes if s <= 4]
```
合格线：MUD 左右各 1 大块（无 ≤4 格碎片）；HIGHSTONE ≤4 格碎片 = 0。

### J.2 边缘质量指标（定位锯齿/伪影）
```python
iso=cnt0=cnt1=diagonly=0
for r in 1..H-2, c in 1..W-2:
    cat=grid[r][c]; 
    if cat not in PAINT: continue
    orth=[grid[r+dr][c+dc] for dr,dc in ORTH]; diag=[grid[r+dr][c+dc] for dr,dc in DIAG]
    cnt=sum(1 for x in orth+diag if x==cat)
    if cnt<3: iso+=1
    if cnt==0: cnt0+=1
    if cat not in orth and any(x==cat for x in diag): diagonly+=1
```
`cleanup` 生效的标志：iso 从 ~156 降到 ~31，cnt0 从 ~21 降到 ~3，diagonly 从 4 降到 2。

### J.3 瓦片级坐标定位（可选增强 · 仅当环境能读图时）
> ⚠️ 本小节是**可选增强**，前提是运行环境**能读取 PNG**（多模态）。若不能读图，**直接跳过本节**，靠 J.1/J.2/J.4 的纯文本指标即可。
出问题但不知道在哪？用 (row,col) → 像素 `(col*TILE, row*TILE)` 裁剪放大某块区域，
而不是靠全图俯瞰猜：
```python
from PIL import Image
im = Image.open('rw_4v4_preview.png'); T=20
im.crop((c0*T, r0*T, c1*T, r1*T)).save('crop.png')     # 只看这一块
im.crop((c0*T, r0*T, c1*T, r1*T)).resize((W*4,H*4), Image.NEAREST).save('zoom.png')  # 4x 放大
```

### J.4 结构校验（不能省的硬检查）
- `validate_tmx` / `K.validate` 零问题（引用闭合、坐标合法、gid 在图集内）。
- decode tmx 复核队伍奇偶（见 `competitive_4v4.md` §1）。
- 水晶落点地形检查：7 个水晶坐标对应的 `grid[row][col]` 必须是可建陆地/滩，不能是深水。

---

> 署名：三方同志｜作者交流 QQ 群：528400691（修边专项补充）
