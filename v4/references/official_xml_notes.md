# 官方触发 XML 格式注意事项（规范原文·精编自包含版）

> 本文件是「铁锈战争触发器 XML 格式规范与最佳实践」的**精编自包含版**，
> 内容足以独立指导写触发，不必再依赖外部 `xml格式注意事项.txt`。
> 原规范作者交流 QQ 群：740214131（内容归属原作者，本 Skill 仅作整理收录）。
>
> **配套阅读**：本文件讲「XML 格式与规范」；**宾语有哪些类型、各类型怎么用、资金（`changeCredits`）与生存地图怎么做、unitDetect 完整条件、单位表**，见姊妹篇 `references/trigger_objects_v26.md`（精编自《铁锈超级详细的触发层宾语教程·图文 v2.6》）。两篇互补，写触发时都要看。

写完触发后，**逐条对照第八节检查清单**自检，再跑 `scripts/verify_tmx.py`。

---

## 一、核心架构规范

### 1.1 强制图层结构
- 唯一正确：所有触发器对象必须放在 `<objectgroup name="Triggers">` 内。
- **绝对禁止**：
  1. 图层名不是 `Triggers`（**大小写敏感**）
  2. 触发器放进其它图层（如 `Ground`、`Units`）
  3. 缺少 `<properties>` 标签
  4. `object` 直接放在根目录

### 1.2 XML 标准骨架
```
<objectgroup name="Triggers">
  <object id="数字" name="触发器名" type="类型" x="X" y="Y" width="宽" height="高">
    <properties>
      <property name="属性名" value="属性值"/>
    </properties>
  </object>
</objectgroup>
```

### 1.3 对象必需属性
每个 `object` 必须包含 6 个属性：`id` / `name` / `type` / `x` / `y` / `width` / `height`。

### 1.4 属性节点规范
每个 `object` 必须有 `<properties>` 子元素，**即使为空也要保留空标签**：
- 正确：`<properties></properties>`
- 错误：完全省略 `<properties>` 节点

---

### 1.5 【可运行级】最小可直接跑的 `objectgroup` 模板
> 上面 1.2 是**结构示意**；这里给的是**复制进 tmx 就能被引擎识别**的完整最小模板。
> 把它整体贴进 tmx 的 `<objectgroup name="Triggers" visible="false">...</objectgroup>` 里即可。

**模板一：绝对最小（一个基本对象 + 一个 map_info）**
```xml
<objectgroup name="Triggers" visible="false">
  <object id="1" name="map_info" x="0" y="0" width="20" height="20">
    <properties>
      <property name="survivalWaves" value="+0:00 开始 - 3 tank"/>
    </properties>
  </object>
  <object id="2" name="hint" type="basic" x="0" y="0" width="20" height="20">
    <properties>
      <property name="message" value="欢迎来到本地图"/>
      <property name="duration" value="5s"/>
    </properties>
  </object>
</objectgroup>
```
> 逐行说明：`id` 全图唯一且为正整数；`name` 用**英文+数字+下划线**（禁中文、连字符、点号、空格）；`type` 才是真正决定对象类别的字段（`basic` 为旁白提示）；`x/y/width/height` 必填；每个 `object` 都必须有 `<properties>`（空也要留）。

**模板二：map_info 必填字段完整版（含多波次 + 胜利条件）**
```xml
<objectgroup name="Triggers" visible="false">
  <object id="1" name="map_info" x="0" y="0" width="20" height="20">
    <properties>
      <property name="survivalWaves" value="+0:00 第一波 - 3 tank&#10;+1:00 第二波 - 2 experimentalHoverTank&#10;[win] 全部波次完成 - 胜利！"/>
    </properties>
  </object>
</objectgroup>
```
> 关键：`survivalWaves` 多行用 **`&#10;`** 换行，不要直接写真实换行；`[win]` 前缀行表示胜利；格式为 `+分:秒 提示文本 - 数量 单位名`。

**模板三：单对象最小骨架（复制改 name/type 即可）**
```xml
<object id="3" name="my_trigger" type="unitAdd" x="100" y="100" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2"/>
    <property name="team" value="1"/>
  </properties>
</object>
```
> 换类型就换 `type`+属性：`basic`=旁白(message/duration)｜`unitAdd`=刷兵(spawnUnits/team)｜`unitDetect`=检测(unitType/team/minUnits)｜`camera_start`=初始视野｜`attack_point`=进攻点。完整 17 类主表宾语（另含 B+ 滚木类型 / B++ 补充类型）见 `trigger_objects_v26.md`；完整可运行样例见其「零」节。

---
## 二、命名规范

### 2.1 对象 name 规范
- **允许**：英文、数字、下划线。
- 正确：`wave_1`、`trigger01`、`spawn_point`、`boss_phase_2`
- **禁止**：中文（`第一波`）、连字符（`wave-1`）、点号（`spawn.point`）、空格（`boss phase`）、特殊符号（`trig@ger`）

> ⚠️ 注意：官方规范要求 name 无中文；但 RW **原图**常出现中文 name（本 Skill 的迁移目标以原图风格为准，改动非目标段时可沿用原名）。**新建触发器如需严谨兼容，建议用英文/数字/下划线**。

### 2.2 单位名大小写规则（精确）
必须严格参照游戏内部代码表，无绝对统一规则，**唯一标准是与单位表完全一致**。
- 单单词：全小写 → `tank`、`scout`、`builder`（错：`Tank`、`SCOUT`）
- 双单词（常见）：第二个单词首字母大写 → `heavyTank`、`hoverTank`、`mechFactory`（错：`heavytank`）
- 特殊单位（必须严格匹配）：
  - `c_tank`（老版坦克，带下划线）
  - `c_artillery`（自行火炮，带下划线）
  - `aaBeamGunship`（首字母缩写 aa 全小写）
  - `bugMeleeT31`（T3 大写表示等级，1 为数字）
  - `wall_v`（城墙，带下划线）
  - `experimentalCarrier`（实验航母）
  - `mammothTank`（猛犸坦克）
  - `laserTank`（激光坦克）

### 2.3 属性名规范
驼峰命名（首单词小写，后续单词首字母大写）：
- 正确：`spawnUnits`、`activatedBy`、`deactivatedBy`、`alsoActivate`、`delay`、`warmUp`、`repeatDelay`、`resetActivationAfter`、`unitType`、`minUnits`、`maxUnits`、`textColor`、`textSize`
- 错误：`spawnunits`、`activatedby`、`warmup`、`unittype`、`textcolor` …
- **例外（保留大写）**：`globalMessage_textColor`、`textOffsetX`、`textOffsetY`
- 布尔值**必须小写**：`true` / `false`（错：`True`、`TRUE`、`1`、`0`）

### 2.4 类型名规范
类型名驼峰：`unitAdd`、`unitDetect`、`moveCamera`、`changeCredits`、`teamInfo`（错：`unitadd`…）
- **例外**：`basic` 全小写（错：`Basic`）

---

## 三、数值规范

### 3.1 坐标与尺寸
- `x` / `y`：0–3000 整数（150 格 × 20 像素），**不能有小数、不能为负**
- `width` / `height`：正整数，**推荐 20 的倍数**（一格 = 20 像素），**不能为 0**
- 有效：`x="1500" y="750" width="100" height="100"`；`x="0" y="0" width="20" height="20"`
- 无效：`x="1500.5"`、`y="-50"`、`width="0"`
- 坐标系统：**左上角 (0,0)**，标准地图 50×120 格 = 1000×2400 像素

### 3.2 时间格式
**所有时间值必须带单位**：`30s`、`5s`、`0.5s`、`100s`（错：`30`、`5`）
- 毫秒：`500ms`、`1000ms`（=1s）
- 支持小数：`warmUp="0.5s"`

### 3.3 ID 唯一性
- 每个 object 的 `id` 必须唯一且为**正整数**：`id="1"`、`id="2"`、`id="100"`
- 错误：`id="object1"`、`id="trigger_1"`、`id="01"`
- 管理原则：逻辑引用**用 name 而非 id**；新建系统建议从 200/300 等整百开始，避免冲突。

### 3.4 team 属性值
- `-2`：所有敌方　`-1`：中立单位　`0`：玩家1（绿）　`1`：玩家2（红）　`2`：玩家3（蓝）…… 最大 = 地图玩家数 - 1
- 常见错误：`team="4"`（地图只有 2 玩家）、`team="player1"`（必须数字）、`team="-3"`

### 3.5 尺寸设计建议
- 单位生成点：20×20（一格）
- 钱箱收集区：60×60（3×3 格）较合适
- 检测区域：按需设置，避免过大影响性能

---

## 四、特殊对象定义标准

### 4.1 map_info（必须且唯一）
- `name="map_info"`（名称固定），每个地图**有且只有一个**
- 必需：`type` ∈ {`skirmish` 遭遇战, `survival` 生存, `mission` 任务, `challenge` 挑战}
- 必需：`winCondition` ∈ {`NONE`, `mainBuildings`, `allUnitsAndBuildings`, `allBuildings`, `commandCenter`, `requiredObjectives`}
  - 注：教程 v2.6 生存模式段落把此处误写成 `winConditions`（多一个 s），以属性定义处的 `winCondition`（单数）为准；教程"常见 bug"也提示"是不是缺了个 s / 多了个 s"
- 可选：`fog`（`NONE`/`los`/`map`）、`introText`（载入文本）；`loseCondition` 在 1.15 已移除

### 4.2 生存模式刷兵点
- `name` 必须包含 `attack_point`：`attack_point_1`、`attack_point_north`（错：`attackpoint`、`spawn_point`）
- **`type` 必须为空**：正确 `<object name="attack_point_1" type="" .../>`；错误 `type="attack_point"`

### 4.3 初始视野
- `name="camera_start"`（固定），可设 `zoomTo` 调整初始视野大小

### 4.4 视野移动
- `type="moveCamera"`；注意 `camera_pan` 在自定义地图中无效

---

## 五、关键数据格式

### 5.1 生存波次（survivalWaves）
严格格式：`分钟:秒数 文本 - 数量 单位名,数量 单位名...`
```
<property name="survivalWaves" value=" 0:30 Wave 1 - 10 tank,5 mechGun
 1:00 Wave 2 - 8 hoverTank,6 mechMissile
 2:00 Wave 3 - 5 heavyTank [win]"/>
```
关键要求：
1. 每行**以空格开头**（一个空格）
2. 时间格式 `分钟:秒数`，**秒数必须两位数**（`05`）
3. 文本与 `-` 之间有空格
4. 单位列表逗号后无空格（或统一一致）
5. 单位名严格匹配单位表大小写
6. `[win]` 必须放最后一波末尾，格式 `5 heavyTank [win]`（`[win]` 前一个普通空格，后无字符）

**隐藏陷阱**：从网页/聊天复制可能引入「不间断空格」导致解析失败；秒数 <10 须补零（`0:05` 对，`0:5` 错）；波次行间用普通 `\n`；末尾不要多余空格/空行。

### 5.2 单位生成（spawnUnits）
格式：`单位名*数量`；多个 `单位名*数量,单位名*数量`；带附加属性 `单位名*数量(属性=值,属性=值)`
- 基础：`tank*3`
- 多个：`heavyTank*2,mammothTank*1`
- 附加：`tank*5(techLevel=2,spawnChance=0.5,falling=true)`
- **关键**：括号必须紧贴数量，**无空格** `tank*5(falling=true)`（错：`tank*5 (falling=true)` 属性失效）
- 常见附加属性：`techLevel`、`spawnChance`(0–1)、`falling`(true/false)、`gridAlign`、`offsetRandomXY`、`neutralTeam`、`offsetHeight`、`offsetDir`(0–360)

### 5.3 连锁触发格式
- 可引用多个：`activatedBy="trigger1,trigger2,trigger3"`、`alsoActivate="effect1,effect2,effect3"`
- 逗号分隔**无空格**；引用的 name 必须存在；避免循环引用

---

## 六、属性值格式

### 6.1 颜色
- 十六进制 `#ff0000`，或简写色名 `red`/`green`/`blue`/`yellow`/`white`/`black`

### 6.2 文本显示
- `mapText`：`text`、`textColor`、`textSize`（数字）、`textOffsetX`/`textOffsetY`（20 为一格）
- `globalMessage`：`globalMessage`、`globalMessage_delayPerChar`、`globalMessage_textColor`

### 6.3 unitDetect 条件属性
`unitType`、`minUnits`、`maxUnits`、`onlyIdle`、`onlyBuildings`、`onlyMainBuildings`、`onlyBuilders`、`onlyAttack`、`onlyAttackAir`

### 6.4 延迟与重复（区分）
- `warmUp`：**条件满足后**延迟 N 秒执行（每次激活都生效）
- `delay`：**开局后**延迟 N 秒**开始检测**（只生效一次）
- `repeatDelay`：重复触发间隔
- `resetActivationAfter`：触发后重置，需要重新满足条件

---

## 七、触发器类型速查

> **本节只列名，不展开。每种类型的完整属性、宾语三大写法（填名称/填类型/填属性）、`changeCredits` 资金详解、生存地图三宾语与完整流程、`unitDetect` 完整条件、单位表，见 `references/trigger_objects_v26.md`（主表 17 类，另含 B+ 滚木类型 / B++ 补充类型）。**

**宾语三大写法**：① 填 `name`（type 空）——`map_info` / `camera_start` / `attack_point`；② 填 `type`（name 随意）——见下 17 类主表（另含 B+ 滚木 / B++ 补充类型）；③ 填 `property`——各属性值。

- **基础/信息**：`unitAdd`(必须有 team)、`unitRemove`、`unitDetect`、`mapText`、`moveCamera`、`camera_pan`(自定义地图无效)、`changeCredits`(资金)、`basic`
- **单位控制**：`move`(配 point)、`point`、`rotate`、`set_team`、`fall`
- **AI 控制**：`team_info`（注：`ai_allow_full_use` / `disable_unit_ai` 属“滚木”类型、自定义地图基本用不到，已移出主表，见 `trigger_objects_v26.md` 的 B+ 节）
- **特殊**：`objective`(配 requiredObjectives)、`teamTags`、`teamTagDetect`

> ⚠️ **`camera_pan` vs `moveCamera`**：2.6 教程中两者是不同东西——`camera_pan` 改屏幕显示区域（**自定义地图无效**）、`moveCamera` 强制移屏。**自定义地图一律用 `moveCamera`。**

---

## 八、验证检查清单（写完逐条对照）

**结构**：① 仅一个 `Triggers` 图层 ② 所有 object 都在其内 ③ 每个 object 6 属性齐全 ④ 有 `<properties>` ⑤ 每个 property 有 name+value

**数据**：① id 唯一数字 ② name 只含英文/数字/下划线（新写时） ③ 单位名大小写严格 ④ 属性名驼峰 ⑤ 布尔小写 ⑥ 时间带 s/ms ⑦ team 值有效 ⑧ map_info 唯一 ⑨ 坐标 0–3000 ⑩ 尺寸不为 0

**逻辑**：① `activatedBy` 引用的 name 存在 ② 无循环引用 ③ 连锁逻辑正确 ④ 条件检测合理 ⑤ 重置机制正确

**生存模式**：① `type="survival"` ② 有 `attack_point`（type 空） ③ survivalWaves 格式正确 ④ 单位名大小写 ⑤ 时间补零 ⑥ 波次间空行

**遭遇战**：① `type="skirmish"` ② 合理 winCondition ③ 玩家初始设置正确

---

## 九、常见错误与修复

| 错误 | 修复 |
|---|---|
| `name="spawnunits"` | `name="spawnUnits"` |
| `name="activatedby"` | `name="activatedBy"` |
| `name="unittype"` | `name="unitType"` |
| `name="textcolor"` | `name="textColor"` |
| `value="Heavytank*3"` | `value="heavyTank*3"` |
| `value="mammothtank*1"` | `value="mammothTank*1"` |
| `value="experiementalCarrier*1"` | `value="experimentalCarrier*1"` |
| `delay="30"` | `delay="30s"` |
| object 放根目录 | 放进 `objectgroup name="Triggers"` |
| 缺 `<properties>` | 补 `<properties></properties>` |
| `activatedBy="不存在的名称"` | 确保引用的 name 存在 |
| A 激活 B、B 激活 A | 重新设计逻辑，去环 |
| `[win]` 前是不间断空格 | 删掉重输普通英文空格 |
| ` 0:5 Wave 1` | ` 0:05 Wave 1` |
| `tank*5 (falling=true)` | `tank*5(falling=true)` |

---

## 十、性能与调试

- **触发器数量**：简单 <100；中等 100–200；复杂 200–300（需优化）；>300 可能卡顿
- **优化**：合并相似触发器；用 `repeatDelay` 代替多个独立触发器；分区激活；`resetActivationAfter ≥ 0.5s`；避免过多 `unitDetect` 同跑、检测区过大
- **调试**：关键节点加 `globalMessage` 输出；用 `mapText` 可视化状态
- **终极解法（格式全对仍报错）**：新建空白文本文件手敲；用正则 `[\x00-\x1F\x7F]` 删所有不可见控制字符；纯净代码整体替换

---

## 十一、版本兼容（1.14 → 1.15）

- 移除：`loseCondition`
- 新增：`spyDrone`、`heavyAAShip` 等单位；模块化蜘蛛新增模块
- 修复：`changeCredits`（1.14 有 bug）；概率生成更稳定
- 兼容建议：避免 1.15 特有单位（如需兼容旧版）、避免已移除属性；在目标版本上测试

---

## 十二、宾语（触发链）简洁技巧

**核心理念**：一个宾语只做一件事；一条链只有一个激活方向（单向流动）；只用必要属性；名字短而有意义。

**极简命名** `[类型]_[玩家]`：
- 前缀：`detect_`(unitDetect)、`spawn_`(unitAdd)、`remove_`(unitRemove)、`relay_`(basic)、`text_`(mapText)、`cam_`(moveCamera)
- 玩家：`p0`–`p9`；`all` 全玩家；`center` 中心节点
- 示例：`detect_p1`、`spawn_p3`、`remove_all`、`relay_center`、`text_d`

**触发链**：多用 `activatedBy`，少用 `alsoActivate`。
- 正确（一眼看出顺序）：`A`(源) → `B activatedBy="A"` → `C activatedBy="B"` → `D activatedBy="C"`
- **中继站模式**（一触多）：源头 → `relay_center activatedBy="源头" alsoActivate="动作1,动作2,动作3"` → 三个动作各自 `activatedBy="relay_center"`（**只有中继站用 alsoActivate**）

**ID 分配**：按范围分组 —— `1000–1999` 左队、`2000–2999` 右队、`3000–3999` 共用/中心；每玩家预留 10 个（p1 用 1100–1109…）

**检查**：名字能看懂吗？触发链清晰吗（只用 activatedBy，除中继站）？时间属性用对了吗？有冗余属性吗（默认值不写）？ID 有规律吗？

---

> 内容整理自《铁锈战争地图触发器XML格式规范与最佳实践指南》（原作者交流 QQ 群：740214131）。
> 本 Skill 署名：三方同志｜作者交流 QQ 群：528400691。
