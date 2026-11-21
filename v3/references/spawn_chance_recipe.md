# 顺序衰减抽签：spawnChance 真正的“随机单位”（实战验证）
> 场景：同一 `unitAdd` 里一次性滴出**真正的随机组合**，而不是每次固定的那一种。
> 本文记录铁锈 `spawnChance` / `maxSpawnLimit` 的**真实引擎行为**（实测 + 引擎推导）。
> **配套可运行脚本**：`scripts/spawn_chance.py`
> ```bash
> # 只算概率分布（不写盘）：先看清各单位真实出场率，再决定给什么 spawnChance
> python3 scripts/spawn_chance.py --units 'mechminigun*1@0.5,mechflame*1@0.4:1,mechlightning*1@0.7:2'
> # 注入到 tmx
> python3 scripts/spawn_chance.py 'X.tmx' --units 'mechminigun*1@0.5' --team 1
> ```
> 单位语法：`name*count@spawnChance:maxSpawnLimit`（例 `mechflame*1@0.4:1`）
> 署名：三方同志｜作者交流 QQ 群：528400691

---

## 0. 结论速查（TL;DR）
- `spawnUnits` 里写多个 `单位*数量(属性)`，**逗号分隔**，引擎会**按顺序逐个撑骰**。
- 每个单位是否生成，是**独立的一次概率判定**（`spawnChance`）；但会**累积计数 + `maxSpawnLimit` 卡上限**。
- 这不是“三选一”，而是“**按顺序逐个尝试、各自决定出不出**” → 天然让**先出场的单位权重更高**。
- 每个单位**真正出场的概率 = 自己撑中 × 前面所有单位都失败**。
- **保底不出空**：把**最后一个单位**设为 `spawnChance=1.0, maxSpawnLimit=1`，空局概率归零。

---

## 1. 示例拆解

```xml
spawnUnits="mechminigun*1(spawnChance=0.5),mechflame*1(spawnChance=0.4,maxSpawnLimit=1),mechlightning*1(spawnChance=0.7,maxSpawnLimit=2)"
```

引擎行为，按顺序逐步执行：

| 步 | 单位 | 动作 |
|---|---|---|
| 1 | 机枪机甲 mechminigun | 50% 概率生成；出了就 +1 |
| 2 | 喷火机甲 mechflame | 40% 概率撑中；但**先查：已生成数 + 这1个 > 1 ？** 超了就**跳过** |
| 3 | 特斯拉机甲 mechlightning | 70% 概率撑中；但**先查：已生成数 + 这1个 > 2 ？** 超了就**跳过** |

所以**能出现的组合只有**：
- 无单位成功生成
- 单机枪 / 单喷火 / 单特斯拉
- 机枪+喷火 / 机枪+特斯拉 / 喷火+特斯拉

> 注：**机枪+喷火+特斯拉** 永远出不来——第3步时已出2个，+1=3 > maxSpawnLimit=2，被跳。

---

### 1.5 【可运行级】完整 `<object>` 外壳（复制即用）
> 前面 1、3 节给的是 `spawnUnits="..."` 的**裸属性值**；引擎真正吃的是**完整 `<object>`**。下面两段取自实战，放进 `random_spawn_recipe.md` 的 `lot_g1_cell*_add` 或任意 `unitAdd` 的出兵器位即可。

**写法 A：纯 spawnChance 随机组合（位置固定，一出兵器内多种单位）**
```xml
<object id="2100" name="reward_random_combo" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="mechminigun*1(spawnChance=0.5),mechflame*1(spawnChance=0.4,maxSpawnLimit=1),mechlightning*1(spawnChance=1.0,maxSpawnLimit=1)"/>
    <property name="team" value="1"/>
    <property name="delay" value="5s"/>
    <property name="activatedBy" value="lot_g1_cell1_det"/>
  </properties>
</object>
```
> 字段逐行：`spawnUnits` 逗号分隔按序撑骰；最后一个 `spawnChance=1.0,maxSpawnLimit=1` 做**保底不空出**；`team` 控制归属（1=游戏内 2 号位）；`delay` 从激活起算；`activatedBy` 填对应探测器 name（若独立出则可省略）。

**写法 B：三格抽签方案里的出兵器（从 random_spawn_recipe.md 拆出，对照看）**
```xml
<object id="2008" name="lot_g1_cell1_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2,experimentalHoverTank*2"/>
    <property name="team" value="1"/>
    <property name="activatedBy" value="lot_g1_cell1_det"/>
  </properties>
</object>
```
> 对照记忆：写法 B 里 `spawnUnits` **没写 spawnChance** → 每个都默认 `1.0` 必出；所以它就是“**必出组合**”，不是随机。想在同一格里也随机，把每个单位的括号属性补上 `spawnChance=` 即可。

**⚠️ 组合铁律（两种可叠加）**
- 位置随机 → 用 `random_spawn_recipe.md` 的三格抽签（offsetRandomX + unitDetect）。
- 出什么随机 → 用本文 spawnChance（同一 unitAdd 内逐个撑骰）。
- 两个一起用：三格抽签决定“在哪出”，每格出兵器里再写 spawnChance 决定“出什么”。
- 千万不要开多个独立 unitAdd 同时抽——**同 delay 会因时间戳种子同步而抽出同一格**（详见 gotchas.md F 段）。

---
## 2. 概率计算公式

> **单个单位出场概率 = 自己撑中概率 × 之前所有单位都失败的概率**

拿上行例子验证：

| 结果 | 计算 | 概率 |
|---|---|---|
| 机枪 | 0.5 | **50%** |
| 喷火 | (1−0.5) × 0.4 = 0.5×0.4 | **20%** |
| 特斯拉 | (1−0.5)(1−0.4) × 0.7 = 0.5×0.6×0.7 | **21%** |
| 无 | 0.5×0.6×0.3 | **9%** |

合计 50+20+21+9 = **100%** ✅

**设计含义**：靠前的单位权重高；越后越低。**不是均匀分布**，而是“**顺序衰减抽签**”。

---

---
## 2.5 为什么必须这样写？——源码级：时间戳作种子

> 上面各种“保底”“抽签”写法，背后都有一个必须绕开的引擎硬伤。看懂这节，你就不会再写出“三个格子永远抽同一格”的图。

### 2.5.1 铁锈的随机到底怎么来的？

铁锈战争源码里，随机数生成器（`Game.rand` / `Bootstrap`）在**每次调用取随机数时，用「当前时间戳」当种子**（而不是一次性生成一个随机序列一直用）。

也就是说：

```
随机值 = f( 系统时间戳 )
```

`f` 是一个**纯函数**——只要输入的时间戳相同，输出的随机值就**完全相同**。

### 2.5.2 致命推论：同一帧的多次抽签，结果必然一样

铁锈的主循环是**按帧处理**的。同一帧内发生的所有逻辑，拿到的“当前时间戳”是**同一个值**。于是：

```
第 N 帧：
  unitAdd#1 抽签 -> 种子 = T
  unitAdd#2 抽签 -> 种子 = T   // 同一帧！
  unitAdd#3 抽签 -> 种子 = T

结论：三次抽签的随机序列完全相同 -> 必然抽中同一格
```

**这不是概率低，而是必然事件。** 所以：

- 多个独立 `unitAdd` 只要 `delay` 一样 → 会在同一帧激活 → 必抽同一格；
- 这也就是 H6 坑的**底层原因**（现象层只是“总出同一格”）。

### 2.5.3 那该怎么绕开？两条正路

| 思路 | 做法 | 适用 |
|---|---|---|
| **A. 把“抽签”塞进单个对象** | 一组 `unitAdd`，用 `spawnChance` 在**同一个对象内**按序撑骰。同一帧同一对象内部的多个撑骰走的是**连续调用**，种子会随调用推进而变化，不会被“同帧同种子”坑到 | 一出兵器内随机出 1 种（见第 1、3 节） |
| **B. 用“信标 + 探测器”物理位置配对** | 信标 `unitAdd` 发射导弹，导弹落点随机（`offsetRandomX`）；落点落在哪个探测器 `unitDetect` 范围内，就激活对应的出兵器 `unitAdd` | 三格/多格大范围抽签（见 `random_spawn_recipe.md`） |

> 关键：**别让多个对象在同一帧各自抽一次**。要么收进一个对象（A），要么用空间位置把随机性“摊开”（B）。

### 2.5.4 一句话记住

> **铁锈的随机 = 时间戳哈希；同帧 = 同种子 = 同结果。**
> 想真随机，就让抽签发生在一个对象内（连续调用），或把抽签空间化（信标落点）。

## 3. 保底技巧：保证一定出单位

> 需求：“想要别没有单位生成” → 就让**最后一个单位** `maxSpawnLimit=1` 并给它 **`spawnChance=1.0`**。

原理：
- 最后一个撑骰**必中**（`spawnChance=1.0`）；
- 它的 `maxSpawnLimit=1` 保证**不被前面的计数卡掉**（它只需 ≥1 的余量）；
- 于是“无单位”概率归零。

示例（机枪/喷火/特斯拉都想要，且不空出）：
```xml
spawnUnits="mechminigun*1(spawnChance=0.5),mechflame*1(spawnChance=0.4,maxSpawnLimit=1),mechlightning*1(spawnChance=1.0,maxSpawnLimit=1)"
```

---

## 4. 与“三格抽签”方案的区别（选型建议）
| 方案 | 原理 | 适合场景 | 缺点 |
|---|---|---|---|
| **三格抽签 + 每格一对组合**（见 `random_spawn_recipe.md`） | `offsetRandomX` 随机落点 + 检测区 | 需要“位置也随机” / 随机源不可靠时 | 结构复杂，需要检测器 |
| **`spawnChance` 顺序衰减抽签**（本文） | 同一 `unitAdd` 内逐个撑骰 | 同一出兵器要**多种单位组合**、位置固定 | 概率不均（靠前权重高）；需要仔细算概率 |

> 两者可**组合使用**：先用三格抽签决定“在哪出”，再用 spawnChance 决定“出什么”。
> 单出兵器内做真随机组合，**优先用 spawnChance**（比多组 unitAdd 更简单，也避开了“时间戳随机种子同步”那个坑）。

---

## 5. 踩坑与注意
1. `spawnChance` 取值范围 `0–1`（小数），不写默认 `1.0`（必出）。
2. `maxSpawnLimit` 是**该单位自身的累计上限**，不是总上限；多个单位各算各的。
3. 概率**不是均匀的**：`spawnChance` 是“裸概率”，**实际出场率要乘前面所有失败率**。算结果分布千万别直接拿 `spawnChance` 当权重。
4. 想看“无单位”概率 = **所有单位全部撑骰失败**的概率连乘。
5. 本文机制是**单个 `unitAdd` 内部**的行为；与“多个 `unitAdd` 同 delay 会因时间戳种子同步”是两回事（后者见 `gotchas.md` F 段、`random_spawn_recipe.md`）。

---

## 6. 一句话经验
> **`spawnChance` = 按顺序逐个撑骰的顺序衰减抽签；真出场率 = 自身概率 × 前面全失败；想要不空出就给最后一个单位 `spawnChance=1.0, maxSpawnLimit=1`。**

> 署名：三方同志｜作者交流 QQ 群：528400691
