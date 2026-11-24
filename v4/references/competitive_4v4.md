# 4V4 竞技遭遇战地图设计范式（Rusted Warfare 1.15 专项）

> 适用：用户要一张 **4v4、左右对抗、纯遭遇战（skirmish）、竞技平衡** 的多人地图。
> 已有两份参考实现：`gen_4v4.py`（铁幕海峡，双海岸+中央海峡+山脊+泥盆）与
> `gen_4v4_rift.py`（干涸裂谷，内陆荒漠河谷+陆桥+方山）。
> 本文件把这些地图**反复踩过、用户骂过**的坑全部固化，照着做就能避开。

---

## 0. 一句话设计哲学

> **纯遭遇战 = 玩家自己打；地图只负责"场地公平 + 海陆空三军各有事干"。**
> 不做剧本、不送单位、不开局播报。胜负 100% 交给玩家。

---

## 1. ★ 最致命坑：队伍奇偶分队（错一次全盘皆输）

铁锈战争多人对局**不是按左右或按出生顺序分队**，而是按 **team 编号的奇偶**：

- **偶数一队**（0/2/4/6），**奇数一队**（1/3/5/7）。
- 4v4 左右对抗的标准配法：**左岸放偶数 0/2/4/6，右岸放奇数 1/3/5/7** → 左右各自成军、正好 4 对 4。

```python
# ✅ 正确（gen_4v4.py 实际写法）：左岸偶数、右岸奇数
def get_spawns():
    tl = [0, 2, 4, 6]          # 左岸 = 偶数队
    tr = [1, 3, 5, 7]          # 右岸 = 奇数队
    return ([(y, LEFT_X, t) for y, t in zip(SPAWN_YS, tl)] +
            [(y, RIGHT_X, t) for y, t in zip(SPAWN_YS, tr)])
```

> ❌ **反例（用户第一次就给错、被骂）**：左岸 0/1/2/3、右岸 4/5/6/7。
> 这在 RW 里会让 0 和 1、2 和 3…… 变成同一队，**左右根本不是 4v4**，直接废图。

**交付前务必 decode tmx 复核**（不能只信代码注释）：

```python
import xml.etree.ElementTree as ET
root = ET.parse(PATH).getroot()
teams = []
for g in root.findall('objectgroup'):
    if g.get('name') == 'UnitObjects':
        for o in g.findall('object'):
            d = {p.get('name'): p.get('value') for p in o.find('properties').findall('property')}
            if d.get('unit') == 'commandCenter':
                teams.append((int(d['team']), int(float(o.get('x')) // 20)))
left  = sorted(t for t, c in teams if c < 90)   # 左岸列 < 中轴
right = sorted(t for t, c in teams if c >= 90)
assert left  == [0, 2, 4, 6], left
assert right == [1, 3, 5, 7], right
```

---

## 2. 地面层整合.tsx + autotile 调用范式

地形**不要自己算 gid**，一律用集成好的自动拼接：

```python
import gen_combined as C          # 封装了地面层整合.tsx 的 autotile
import gen_koth as K              # 封装了渲染/组装/校验

grid = [[GRASS] * SIZE for _ in range(SIZE)]   # 先填"地形角索引矩阵"
# ... 在此之上铺山/水/沙/泥/高石 ...
ground_tid = C.autotile(grid)                    # 四角对角线自动拼接 → tid 矩阵
ground = [[K.GROUND_FG + ground_tid[r][c] for c in range(SIZE)] for r in range(SIZE)]
```

**地形角索引表（来自 地面层整合.tsx 的 terraintypes，本项目约定）：**

| 值 | 地形 | 备注 |
|---|---|---|
| 0 | 草 grass | 基底 / 出生点 |
| 1 | 土 dirt | 点缀 |
| 2 | 石 stone | 山体 / 碎石地 |
| 3 | 沙 sand | 干旱前线 |
| 4 | 泥 mud | 洼地（cliff，不可通行） |
| 7 | 水 water | 河 / 湖 / 海 |
| 8 | 海 sea | |
| 9 | 洋 ocean | |
| 12 | 高草 highGrass | 森林 / 丘陵（悬崖边） |
| 14 | 高石 highStone | **高山 cliff，不可通行** —— 天然屏障 |
| 23 | 浅滩 shoal | 登陆滩 |

> 通用地形铁律（四邻 ≤ 2 种地形、成片才可见、兼容矩阵）见 `terrain_compat.md` 与
> `terrain_generation.md`，本文件不再重复。

---

## 3. 纯遭遇战 Triggers 约束（干净对局）

`Triggers` 对象组**只放两样**，其余一律不写：

```xml
<objectgroup name="Triggers">
  <object id="1" name="map_info" type="" x="90" y="70" width="224" height="136">
    <properties>
      <property name="type" value="skirmish"/>
      <property name="winCondition" value="mainBuilings"/>
      <property name="fog" value="los"/>
    </properties>
  </object>
  <object id="2" name="camera_start" type="camera_start" x="90" y="90" width="20" height="20"/>
</objectgroup>
```

红线（逐条都踩过）：
- **不要** `unitDetect` / `unitAdd` / `changeCredits` 等任何触发器逻辑宾语。
- **不要** `introText` / 开局播报（纯遭遇战无脚本事件）。
- `map_info` 必须且唯一；`winCondition=mainBuilings`（主基地决定胜负）。
- 初始单位（主基地、工程兵、水晶）**必须放 `UnitObjects` 图层**，不是 Triggers；否则一开局判负（见 SKILL §3.2 坑 9）。

---

## 4. 让海陆军主导、空军只当辅助（竞技地图的硬要求）

用户明确要求"**不能让空军作用很大**"。做到三件事：

1. **决定性经济点（水晶 `crystalResource`）全部落在岛/桥/浅滩上** —— 空军无法占领，
   必须由**海军登陆**或**陆军越桥/越陆**去抢 → 经济命脉不在天空。
   ```python
   crystals = [(90, 90), (90, 88), (90, 92), (90, 40), (90, 140), (80, 90), (100, 90)]
   for (cc, rr) in crystals:
       add_unit("crystalResource", -1, cc * 20, rr * 20)   # team=-1 中立，谁抢到算谁的
   ```
2. **基地紧贴海岸/河谷**（海军一开局卷入），背靠山地屏障（陆军强攻需走隘口）。
3. 地图主体用大面积陆地 + 河道/海峡，给陆海留出主战场；不要做空旷大平原让飞机横行。

> 反例：把水晶放内陆平原 = 空军直接抢光 = 游戏失衡。

---

## 5. 平衡性（竞技地图的命根子）

### 5.1 镜像对称布置（最稳的平衡法）
山脊、森林、资源带、出生点**全部以中轴成对** → 左右几何等价，无人能挑刺。
裂谷图（`gen_4v4_rift.py`）就是全图 `mirror()` 镜像生成，保证左右完全对称。

### 5.2 资源带左右覆盖率一致
泥盆 / 资源带**不要**左右各用不同噪声 → 会出现"左盆 1787 格 / 右盆 616 格"3 倍失衡。
正确做法：每侧**自动搜索覆盖率**，让两侧最终格数都逼近同一目标（如 850），并只留最大连通片：

```python
# 每侧在多个候选覆盖率里挑"最终格数最接近目标"的那个 → 左右天然平衡
for side in (0, 1):
    best_mask, best_n = None, -1
    for qcov in (0.38, 0.44, 0.50, 0.56):
        mask, n = _mud_side(side, qcov)
        if best_n < 0 or abs(n - 850) < abs(best_n - 850):
            best_mask, best_n = mask, n
    ...
```
> 实测：左 1445 / 右 1383（差 4%），肉眼已无法分辨失衡。

### 5.3 每队资源量等价
- 每队 **2 个起步矿**（`res_pool`，放在 `Items` 层，GID = `MISC_FG + _RES_POOL_TILE`），全图 16 个。
- 矿必须落在**可建陆地**上：先 `protect_bases()` 清掉基地草芯上的山/水，再 `place_res()`
  用螺旋就近找可建格（目标格被占就外扩搜索），保证每队稳定 2 矿。

### 5.4 出生点质量等价
每队：1 个 `commandCenter` + 2 个 `builder`（工程兵，放背侧与侧翼草芯）。
基地周围半径内强制纯草（`protect_bases` 的曼哈顿半径 ≤2 清场），否则单位卡住。

---

## 6. 风格多样化（避免两张图雷同）

用户原话："**风格不要和你上一份 4V4 太像**"。两套已实现风格可参考，做新图时换一套：

| 维度 | 铁幕海峡（gen_4v4.py） | 干涸裂谷（gen_4v4_rift.py） |
|---|---|---|
| 主体 | 两片海岸陆块被大洋隔开 | 一整块内陆大陆，无海洋 |
| 中央分隔 | 南北贯通宽海峡 | 蜿蜒河谷（蓝水+浅滩岸） |
| 调色 | 满屏绿地 | 中央荒漠带（沙/土波浪边），绿地 homeland 两翼 |
| 岩石 | 连续长山脊（屏障） | 散落圆方山/孤峰（掩体+视野遮挡） |
| 植被 | 中央高草台地 | 贴基地森林丛 + 小沼泽 |
| 水晶 | 远海岛屿（海军抢） | 河谷小岛 + 陆桥（海军+陆军争夺） |

**换风格的旋钮**：主体（海陆占比）、分隔物（海峡/河谷/山脉）、调色（绿洲/荒漠/雪原）、
岩石形态（长脊/方山/碎石）、植被（森林/高草/沼泽）、水晶位置（岛/桥/谷）。

---

## 7. 交付前自检清单（逐条过）

- [ ] **decode tmx 复核队伍**：左岸=[0,2,4,6]、右岸=[1,3,5,7]（§1 脚本）。
- [ ] `validate_tmx` / `K.validate` 零问题（引用闭合、坐标合法）。
- [ ] Triggers 只有 `map_info` + `camera_start`，无脚本宾语（§3）。
- [ ] 16 个起步矿（每队 2），全部在可建陆地（§5.3）。
- [ ] 7 个水晶，全部落在岛/桥/浅滩（空军抢不到，§4）。
- [ ] 每队 commandCenter + 2 builder，基地半径内纯草。
- [ ] 修边质量：见配套 `edge_cleanup.md`（孤立尖刺、对角伪影、锯齿、装饰污染）。
- [ ] 左右资源/地形视觉平衡（§5.1–5.2）。

---

## 8. 交付物管理（别堆 50 份垃圾）

用户曾因产物堆到 50 份而发飙。**只保留**：最终 `.tmx` + 1 张标注版预览图。
- `*_preview.png` 仅供人眼检查，交付前可删；**别把中间调试裁剪图（`crop_*.png` 等）塞给用户**。
- 生成器 `.py` 可保留作为可复现脚本，但同一地图不要留多个版本碎片。

> 署名：三方同志｜作者交流 QQ 群：528400691（4V4 专项补充）
