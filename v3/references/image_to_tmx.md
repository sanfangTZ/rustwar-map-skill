# 图片转地形 TMX（Image → Pure Terrain TMX）
> **一句话**：给一张图片，直接产出一张**能正常运行的纯地形 tmx**（只有 Ground 层，**无任何单位**）。
> 对应脚本：`scripts/png_to_tmx.py`。
> **配套急救脚本**：`scripts/add_layers.py`（游戏报「项目层没找到 / 地面层没找到」时，一键补齐 Ground/Items/Units 三层）
> ```bash
> python3 scripts/add_layers.py 'X.tmx' --check   # 体检：缺哪些必需层
> python3 scripts/add_layers.py 'X.tmx'           # 原地补齐缺失层（自动 .bak 备份）
> ```
> 算法来源：**逆向 `图片转地图_1.0.apk`（包名 `com.pngtotmx.moyang`）全链路破译 + 实测验证**。

---

## 1. 它和「地形生成方法论」的区别

| | `terrain_generation.md` | 本文（图片转 TMX） |
|---|---|---|
| 输入 | 你**设计**的二维地形矩阵（噪声/峰丛/水网） | **一张任意图片** |
| 思路 | 先想地形，再渲染 gid | **把图片亮度当"地形标尺"**，直接查表出 gid |
| 输出 | gids 层 JSON → 再拼 tmx | **一步到位出完整 tmx** |
| 适用 | 追求平衡性/可控地形 | 快速出图、手绘底图、把美术图变成地图 |

两者**互补**：想精细可控走前者；想"拿张图就跑"走本文脚本。

---

## 2. 破译原理（逆向结论，逐条可验证）

### 2.1 主链路（apk 里就是这么干的）
```
BitmapFactory.decodeFile(path)      # 读图
  → getWidth()/getHeight()          # 取尺寸
  → 双重循环 getPixel(x,y)          # 逐像素
  → R = Color.red(pixel)            # ★只看红色分量 0~255
  → 按 8 段阈值查表 → gid           # 填进一维数组 v35[]
  → 每 gid 写 4 字节小端            # struct.pack('<I')
  → GZIP 压缩                       # gzip.compress
  → Base64 编码                     # base64.b64encode
  → 拼 TMX XML → 写盘
```

### 2.2 ★核心铁证：判定依据是「红色分量」
读 apk 的 smali，`Color.red(pixel)` 就是唯一判定量：
```smali
.method public static rn_3901(I)I
    invoke-static {p0}, Landroid/graphics/Color;->red(I)I
    move-result p0
    return p0
.end method
```
**推论**：
- 图片的**红通道**决定地形；绿/蓝/透明度**完全被忽略**。
- 所以"灰度图"能用（R=G=B）；彩色图**也能用**——只认红。
- 想要哪块变成水？**把它画成深红偏暗**即可（R 越小地形越"水"）。

> 细节：apk 内是 `Color.red`，等价于 `(pixel >> 16) & 0xFF`。脚本里用 PIL 直接取 `r`。
> apk 里那一堆 `0x1aaeb8 ^ ...` 的"开关"是**控制流平坦化混淆**，与算法无关，可忽略。

### 2.3 阈值 → GID 映射表（8 段，脚本严格对齐）
| 红色分量 R | GID | 地形 | firstgid 对照 |
|---|---|---|---|
| `R < 32`  (0x20) | **182** | Water（深水） | ✅ |
| `R < 64`  (0x40) | **176** | Shallow Water（浅水） | ✅ |
| `R < 96`  (0x60) | **36**  | Ice（冰） | ✅ |
| `R < 130` (0x82) | **46**  | Snow（雪） | ✅ |
| `R < 160` (0xA0) | **126** | Long Grass（长草） | ✅ |
| `R < 190` (0xBE) | **511** | Stone（石，504+7） | ✅ |
| `R < 210` (0xD2) | **555** | Sand（沙） | ✅ |
| `R < 240` (0xF0) | **544** | Stone Lava Ridge（岩浆，540+4） | ✅ |
| `else`            | **544** | 同岩浆（最亮档兜底） | ✅ |

> **记忆口诀**：**越暗越"水"，越亮越"岩浆"**。红分量从 0 涨到 255，地形依次：
> 深水 → 浅水 → 冰 → 雪 → 长草 → 石 → 沙 → 岩浆 → 岩浆。

---

## 3. 脚本用法

### 3.1 位置
`scripts/png_to_tmx.py`

### 3.2 命令格式
```bash
python3 scripts/png_to_tmx.py <输入图片> <输出.tmx> \
    [--size 140x140] [--theme auto|water|ice|snow|grass|stone|sand|lava] \
    [--map-name 地图名] [--no-triggers] \
    [--auto-stretch] [--bg-spread] [--bg-tol 12]
```

| 参数 | 说明 |
|---|---|
| `<输入图片>` | png/jpg 等，PIL 可读即可 |
| `<输出.tmx>` | 生成的 TMX 路径 |
| `--size WxH` | 地图格数，默认 `140x140`（铁锈地图基准）。图片会被 **NEAREST 缩放**到该尺寸 |
| `--theme` | 主题色板。`auto`=用默认 8 段表；其余为单主题（整图基本一种地形） |
| `--map-name` | TMX 里的名字 |
| `--no-triggers` | 不加 Triggers 段（纯 Ground 层） |
| `--auto-stretch` | **自适应拉伸**：把图片实际 R 范围 `[min,max]` 线性等分 8 档，让浅色图也能铺满地形 |
| `--bg-spread` | **背景打散**：自动识别占比最高的背景色（如白底），把这些背景像素均匀铺满 8 种地形，只让前景按亮度映射 |
| `--bg-tol` | 背景色容差 0-255，默认 `12`，越大识别背景越宽松 |

> **默认行为 = 严格照 apk**（固定 8 段阈值）。`--auto-stretch` / `--bg-spread` 是**增强项**，
> 仅在你觉得"地形太单调"时加，用来适配**浅色/白底图**。

### 3.3 示例
```bash
# ① 原味版：严格照 apk 的固定阈值（默认）
python3 scripts/png_to_tmx.py my_art.png out.tmx --size 140x140 --map-name 艺术岛

# ② 增强版：白底插画/证件图专用（推荐组合）
python3 scripts/png_to_tmx.py my_art.png out.tmx --size 140x140 \
    --map-name 艺术岛 --auto-stretch --bg-spread

# ③ 验证刚才生成的对不对
python3 scripts/verify_tmx.py out.tmx
```

### 3.4 白底图攻略（重要）

**症状**：白底插画/证件照跑原味版，**岩浆占比高得离谱**（如 56.9%）。
**根因**：apk 算法只认红色分量，而白色 R=255 落在最高档 `else → 岩浆`。
一张白底图若有 30% 纯白背景，就有 30% 是岩浆。

**三步解决**：
1. 先跑原味版，看统计里 `lava` 占比是否异常高（>40% 基本可判定为白底/浅底图）。
2. 对浅色图加 `--auto-stretch`（把 R 范围拉伸到满 8 档），地形会丰富一些。
3. 若背景是**大面积纯色**，直接上 `--bg-spread`：脚本会把背景像素**打散**到 8 种地形，
   前景才按真实亮度映射。实测：岩浆 56.9% → 15.7%，8 档最高占比降到 21%。

> **注意 `--bg-spread` 的取舍**：它会让背景变成"随机地形噪点"。
> 想要背景干净（比如纯岩浆背景），就**别加**这个选项——这取决于你要的是"好看"还是"忠于原图"。

**为什么不用"分位数等分"？**（踩坑记录）
最初 `--auto-stretch` 用分位数切 8 档，结果白底图 255 严重扎堆，
7 个切点被挤成 `[58,108,182,232,255,255,255]`（去重只剩 5 个），
档位不足导致**两版输出一模一样**。改用 **R 范围线性等分** `lo + span*k/8` 后，
对扎堆天然免疫，任意图都稳定出 8 档。这是一个真实踩过的坑，特此记录。

---

## 4. 输出规格（与游戏兼容）

- **map 头**：`width/height` = `--size`；`tilewidth=tileheight=20`；`trans=008a76` 色键。
- **数据层**：`encoding="base64" compression="gzip"`，内容是 **小端 uint32 gid 数组**。
  - 生成：`struct.pack('<%dI', *gids)` → `gzip.compress(..., 9)` → `base64.b64encode`（76 字符折行）。
- **tileset**：11 段模板（firstgid 1/36/46/126/176/182/183/204/225/243/504/540/555），**原样复用即合法**。
- **Triggers**：含一个 `map_info` 对象（默认开启，可用 `--no-triggers` 关）。

---

## 5. 实测记录（脚本已验证）

| 项 | 结果 |
|---|---|
| 测试图 | 140×140 灰阶渐变 + 白椭圆 |
| 输出 | `test_out.tmx`，2453 字节 |
| 命中地形 | **8 种全命中**（water/shallow/ice/snow/grass/stone/sand/lava） |
| 自洽校验 | 解码数据块重算，`match = True` |
| `verify_tmx.py` | `XML_OK / Triggers 对象数 1 / 悬空引用无 / 总体 PASS` |

---

## 6. 使用诀窍 & 踩坑

1. **想让某区域变水/冰**：把该区域画成**暗红**（R 小）；想要石/沙/岩浆：画成**亮红**。
2. **尺寸不必等于图片尺寸**：脚本会自动 NEAREST 缩放到 `--size`，所以**任意图片都能用**。
3. **只用红色通道**：绿/蓝随便涂，不影响结果。灰色图最直观。
4. **岩浆/石要成片**：和地形生成一样，地形跳变太多会导致 tile 过渡不自然（图集里没有的过渡组合会被顶点采样兜底）。
5. **`--no-triggers`**：只要纯地形不要触发时用；正常要能玩建议保留（含 map_info）。

---

## 7. 逆向档案（备查）

- 目标 apk：`图片转地图_1.0.apk`（`com.pngtotmx.moyang`，246364 B，md5 `d1a4ae0c3c8827a9e462ab446083f8ea`）
- 关键 smali：`rn_3870.smali#rn_3901`=`Color.red`；`rn_1$6.smali#run`=主循环；`rn_3342.smali#rn_3360`=Base64；`rn_4510.smali`=像素工具。
- 模板来源：apk 内 `assets/data.txt`（213 行 tileset + Triggers 模板）。

---
> 署名：三方同志｜作者交流 QQ 群：528400691


---

## 4. 铁锈战争容器约束（必读）

### 4.1 地面层名必须为 `Ground`（否则地图加载失败）

铁锈战争加载 tmx 时会**强制查找名字为 `Ground` 的 tile layer**，对应游戏内的“地面”层。
若层名不符合，游戏会报错：

```
加载地图错误：地图中找不到"地面"层，这层是必需的
```

**踩坑记录**：脚本早期版本把 `<layer name=...>` 错误地绑定成了 `--map-name`（地图名），
导致生成的 tmx 层名是「测试图片转地图」而不是 `Ground`，游戏直接拒绝加载。

**已修复**：`build_tmx()` 中地面层名**硬性写死为 `Ground`**，与 `--map-name` 完全解耦。
`--map-name` 现在仅作为备注，不影响层名。

正确写法：

```xml
<layer name="Ground" width="140" height="140">
  <data encoding="base64" compression="gzip">...</data>
</layer>
```

### 4.2 地图名称来源

游戏地图列表中显示的名字 = **tmx 文件名**（去掉扩展名），例如
`测试图片转地图.tmx` → 游戏内显示「测试图片转地图」。

### 4.3 游戏地图目录（本机实测）

铁锈战争使用**自定义目录名 `rustedWarfare`**（不是标准 Android 包名路径）。
本机实测游戏实际读取的目录为：

```
/storage/emulated/0/rustedWarfare/maps
```

（该目录下有 `.rwinfo` 标记文件 + 官方 `Map01.tmx`；另有旁路目录
`/storage/emulated/0/Download/QQ/rustedWarfare/maps`，两处均可投放，
游戏优先级以实际读取为准。）

直接 `cp 你的图.tmx /storage/emulated/0/rustedWarfare/maps/` 即可。

### 4.4 纯地形地图必须包含三层：Ground / Items / Units

铁锈战争按顺序检查图层，缺一层就报错：

| 顺序 | 层名 | 游戏内显示 | 纯地形地图怎么填 |
|---|---|---|---|
| 1 | `Ground` | 地面 | 图片转换出的地形 gid |
| 2 | `Items` | 项目 | **全部填 0**（无物品） |
| 3 | `Units` | 单位 | **全部填 0**（无单位） |

**踩坑记录（两连击）**：
1. 刚开始只写了 Ground 层，层名还是错的 → 报“找不到地面层”。
2. 修好 Ground 层名后，又报“项目层没有找到” → 因为压根没写 Items 层。
3. 补上 Items 后，还需补 Units 层（否则会继续报“单位层”）。

**已修复**：`build_tmx()` 现在固定输出 **Ground → Items(全0) → Units(全0)** 三层，
与 `随机单位的生存2.0.tmx` 等正常地图结构一致。

> 注：更复杂的地图还有第 4 个 `Set` 层（占位层），纯地形图不需要。

#### `Set` 层判定条件（什么图需要、什么图不需要）

`Set` 是**可选的第 4 个 tile layer**，位于 `Units` 之后，用于给复杂/官方战役类地图做占位。判断规则：

| 地图类型 | 是否需要 `Set` 层 | 说明 |
|---|---|---|
| **纯地形图**（图片转出来的、只有 Ground 地形） | ❌ **不需要** | 三层 `Ground/Items/Units` 就够，加了反而多余 |
| **普通遭遇战 / 普通剧情图** | ❌ **不需要** | 触发器走 `Triggers` 对象图层，与 `Set` 无关 |
| **官方战役 / 复杂脚本图**（原图里本来就带 `Set`） | ✅ **保留** | 若你改的是本来就含 `Set` 的图，**不要删**，按原样保留 |
| **从零新建的复杂图** | ⚠️ **可选** | 不写也能跑；只有当你要对齐官方图结构时才加一个空的 `Set` |

**关键结论**：
- **`Set` 层不是硬性条件**——缺失不会导致拒载（`check_container.py` 的 C10 只会给「提示」而非 FAIL）。
- **误加一个空的 `Set` 层也不影响加载**，但它没有实际作用，纯地形图建议不要加。
- **判断口径**：如果原图有 `Set` 就保留，原图没有就别加。一句话——**「跟随原图，不强求」。**
