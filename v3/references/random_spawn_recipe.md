# 随机单位刷兵配方（实战验证）
> 场景：开局后某时刻，从若干兵种里**随机**刷兵，且希望结果「每次开局都不同」。
> 本文是 2026-10 实战一次成型的完整方案，含失败教训。
> **配套可运行脚本**：`scripts/random_spawn.py`
> ```bash
> python3 scripts/random_spawn.py 'X.tmx' --dry-run   # 预览将生成的 7 个对象
> python3 scripts/random_spawn.py 'X.tmx' --team 1    # 原地注入（自动 .bak 备份）
> ```
> 署名：三方同志｜作者交流 QQ 群：528400691

---

## 0. 结论速查（TL;DR）

- 铁锈的 `unitAdd` **默认把单位刷在矩形中心，不会自动随机铺开**。
- 要随机落点，**必须显式加 `offsetRandomX` / `offsetRandomY` / `offsetRandomXY`**。
- **用 `offsetRandomX`（仅横向）而不是 `offsetRandomXY`（带 y 偏移）**，避免单位跑出细条状检测区。
- **坐标必须是 0–3000 的正整数**，负坐标会被 clamp（归零/归位），导致多个检测区**重叠**。
- 「三格抽签」方案：1 个抽签器随机落三格之一，每格一颗探测器 + 一个出兵器。
- **想要「每次必出 2 种、各 2 个」→ 每格直接刷「一对组合」**，不要用两组独立抽签（会撞车同步→出 4 个相同）。

---

## 1. 核心机制原理

### 1.1 unitAdd 的落点规则
铁锈 `unitAdd` 在矩形区域内刷兵时，**默认取矩形中心点放一个单位**（不是区域内随机散布）。

| 写法 | 实际效果 |
|---|---|
| `spawnUnits="experimentalTank*2"` | 2 个单位堆在**矩形中心** |
| `spawnUnits="experimentalTank*2(offsetRandomX=120)"` | 每单位在 **x 轴 ±120 像素内随机**，y 不变 |
| `spawnUnits="experimentalTank*2(offsetRandomXY=120)"` | x/y 都随机，**y 也会漂** |

> ⚠️ 踩坑：`offsetRandomXY` 会带来 **y 向偏移**。如果探测器是**高仅 40px 的细条**，单位一 y 漂就可能跑出检测区，导致触发失败。**只做横向抽签时一律用 `offsetRandomX`。**

### 1.2 随机源与「同帧同步」
同一 `delay` 刷出的多个 `unitAdd`，**会被引擎在同一帧处理，共享同一随机种子**。

**后果**：两组独立抽签器若 `delay` 相同，会**永远抽到同一格**（同步随机），结果就是「4 个相同兵种」而不是「2+2 两种」。

**验证现象**：用户实测六遍全是「四个相同」，且三选一（4坦克/4悬浮/4火蜂）——这**说明随机本身生效了**，但两组同步了。

---

## 2. 推荐方案：三格抽签 · 每格一对组合

### 2.1 结构（只需 1 组）
```
抽签器 unitAdd(delay=30s, mechMissile(offsetRandomX=120))
   ├─ 探测器1 (x 覆盖左格)  → 出兵器1 → 兵种A*2,兵种B*2
   ├─ 探测器2 (x 覆盖中格)  → 出兵器2 → 兵种B*2,兵种C*2
   └─ 探测器3 (x 覆盖右格)  → 出兵器3 → 兵种C*2,兵种A*2
```

**为什么每格刷「一对组合」？**
- 无论抽中哪格，都**保证出 2 种不同兵种、各 2 个**。
- 三种组合两两配套，**永远不出现「同一种 4 个」**。
- **只用一组**，从源头杜绝「两组撞同格」。

### 2.2 坐标布局（关键）
假定三个探测器横向紧密排列，每格宽 `cellW`：

| 对象 | x | width | 说明 |
|---|---|---|---|
| 探测器1 | 80 | 80 | 覆盖 80–160 |
| 探测器2 | 160 | 80 | 覆盖 160–240 |
| 探测器3 | 240 | 80 | 覆盖 240–320 |
| 抽签器 | **200** | 20 | **三格中心**，`offsetRandomX=120` → 落点 x∈[80,320] |

- 三格无缝：80–160 / 160–240 / 240–320。
- 抽签器中心 x=200，`offsetRandomX=120` → 随机 x∈[80,320]，**恰好覆盖三格**。
- **y 方向**：抽签器 y 要在探测器 y~y+height 之内（用同高或居中）。

> ⚠️ 一定要算准：抽签器矩形 + offsetRandomX 的**最左/最右**要覆盖到**第1格左边缘 / 第3格右边缘**，否则某格永远抽不中。

### 2.3 最小可用的 XML 骨架
```xml
<!-- 抽签器：机械甲随机落到三格之一 -->
<object id="2004" name="lot_ticket" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/>
    <property name="team" value="-2"/>
    <property name="delay" value="30s"/>
  </properties>
</object>

<!-- 探测器 x3 -->
<object id="2005" name="lot_cell1_det" type="unitDetect" x="80" y="2600" width="80" height="40">
  <properties>
    <property name="unitType" value="mechMissile"/>
    <property name="team" value="-2"/>
  </properties>
</object>
<!-- cell2_det x=160, cell3_det x=240 同理 -->

<!-- 出兵器 x3：每格刷一对组合 -->
<object id="2008" name="lot_cell1_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="experimentalTank*2,experimentalHoverTank*2"/>
    <property name="team" value="-2"/>
    <property name="activatedBy" value="lot_cell1_det"/>
  </properties>
</object>
<!-- cell2_add: experimentalHoverTank*2,fireBee*2 -->
<!-- cell3_add: fireBee*2,experimentalTank*2 -->
```

### 2.4 检测机制要点
- 抽签器刷的机甲**永久存在**，探测器一旦检测到就**保持激活态**（`resetActivationAfter` 不写则只触发一次）。
- 探测器**不需要** `delay`（由抽签器的 delay 控制时序）。
- 出兵器用 `activatedBy` 绑定对应探测器 name。
- 抽签器与探测器 `team` 要一致（本例 -2）。

---

### 2.5 【可运行级】完整 7 对象真实 XML（取自 `随机单位的生存2.0.tmx`）
> 上面 2.3 是骨架；这里是**真实成品地图里能跑的完整版**，7 个对象一个不缺，复制进 `<objectgroup name="Triggers">` 即可用。
> 规律：`ticket`（抽签器）+ `cell1/2/3_det`（探测器，与 ticket 同 team=-2 配对）+ `cell1/2/3_add`（出兵器，`activatedBy` 对应探测器）。

```xml
<!-- ① 抽签器：导弹随机落到三格之一（x=200, offsetRandomX=120 → x∈[80,320]） -->
<object id="2004" name="lot_g1_ticket" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/>
    <property name="team" value="-2"/>
    <property name="delay" value="30s"/>
  </properties>
</object>

<!-- ②③④ 三个探测器：检测覆盖区内是否出现 team=-2 的 mechMissile -->
<object id="2005" name="lot_g1_cell1_det" type="unitDetect" x="120" y="2620" width="40" height="40">
  <properties>
    <property name="unitType" value="mechMissile"/>
    <property name="team" value="-2"/>
    <property name="minUnits" value="1"/>
  </properties>
</object>
<object id="2006" name="lot_g1_cell2_det" type="unitDetect" x="200" y="2620" width="40" height="40">
  <properties>
    <property name="unitType" value="mechMissile"/>
    <property name="team" value="-2"/>
    <property name="minUnits" value="1"/>
  </properties>
</object>
<object id="2007" name="lot_g1_cell3_det" type="unitDetect" x="280" y="2620" width="40" height="40">
  <properties>
    <property name="unitType" value="mechMissile"/>
    <property name="team" value="-2"/>
    <property name="minUnits" value="1"/>
  </properties>
</object>

<!-- ⑤⑥⑦ 三个出兵器：真正刷给玩家的敌人，team=1 即游戏内 2 号位，activatedBy 绑定对应探测器 -->
<object id="2008" name="lot_g1_cell1_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2,experimentalHoverTank*2"/>
    <property name="team" value="1"/>
    <property name="activatedBy" value="lot_g1_cell1_det"/>
  </properties>
</object>
<object id="2009" name="lot_g1_cell2_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="experimentalHoverTank*2,fireBee*2"/>
    <property name="team" value="1"/>
    <property name="activatedBy" value="lot_g1_cell2_det"/>
  </properties>
</object>
<object id="2010" name="lot_g1_cell3_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="fireBee*2,tank*2"/>
    <property name="team" value="1"/>
    <property name="activatedBy" value="lot_g1_cell3_det"/>
  </properties>
</object>
```
> ⚠️ 注意：**出兵器带 `team` 用来控制归属**（这里 =1 给 2 号位）；**ticket 和探测器必须用同一个 team（这里 -2）才能配对**。若想让出兵器变中立敌对，把出兵器 team 改成 -2 即可（但抽签配对不受影响）。

---
## 3. 踩坑全记录（血泪）

| # | 坑 | 后果 | 修复 |
|---|---|---|---|
| 1 | 抽签器/探测器用了**负坐标** y=-200/-400 | 被 clamp → 三格重叠 → 每次同一种怪 | 搬到地图内合法空地（如底部 y=2600+） |
| 2 | 以为 `unitAdd` 会自动随机铺开 | 单位全堆矩形中心 | 显式加 `offsetRandomX` |
| 3 | 抽签器 x=100 w=240 → 中心=220 | 恰好落第2格 → 永远出第2格兵种 | 抽签器移到三格正中 x=200 |
| 4 | 用 `offsetRandomXY` | y 漂移，单位跑出 40px 检测区 | 改 `offsetRandomX` |
| 5 | 两组独立抽签 + 同 delay=30s | 同步随机 → 永远撞同格 → 4 个相同 | 改单组 + 每格一对组合 |
| 6 | heredoc 写中文脚本吞回显 | 看不到输出 | 落盘 `cat > /tmp/x.py` → `python3 x.py > /tmp/o` → `cat /tmp/o` |
| 7 | Python 脚本漏 `import re` | NameError（但文件已写入） | 每脚本确认 import |

---

## 4. 校验清单（改完必跑）

```python
import re, hashlib
import xml.etree.ElementTree as ET
raw = open(P, encoding='utf-8').read()
ET.fromstring(raw)                                      # ① XML 合法
names = re.findall(r'<object[^>]*name="([^"]+)"', raw)
assert len([n for n in names if n.startswith('lot_')]) == 7   # ② 对象数=1票+3探+3出
assert not re.findall(r'x="-\d+"|y="-\d+"', raw)      # ③ 无负坐标
for m in re.finditer(r'<object[^>]*name="(lot_cell\d_add)"[^>]*>(.*?)</object>', raw, re.S):
    su = re.search(r'name="spawnUnits" value="([^"]+)"', m.group(2))
    ab = re.search(r'name="activatedBy" value="([^"]+)"', m.group(2))
    print(m.group(1), su.group(1), ab.group(1))          # ④ 出兵器各有一对组合+activatedBy
print(hashlib.md5(raw.encode('utf-8')).hexdigest())      # ⑤ 记录 MD5 供部署比对
```

---

## 5. 兵种速查（本图相关）
| 中文 | 内部名 |
|---|---|
| 实验坦克 | `experimentalTank` |
| 实验悬浮坦克 | `experimentalHoverTank` |
| 火蜂战机 | `fireBee` |
| 小防空机甲 | `mechMissile` |

---

## 6. 一句话经验
> **随机 = 一格一兵种 + 横向 offsetRandomX 抽签；要「必出多兵种」就把组合直接写进每格的 spawnUnits，不要靠多组独立抽签——它们会同步。**
