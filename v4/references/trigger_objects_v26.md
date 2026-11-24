# 触发层宾语完全手册（精编自 2.6 图解教程）

> 本文件精编自《铁锈超级详细的触发层宾语教程（图文 v2.6）》，
> 原作者：斐比寻常W'213（QQ 2441054858）；资金章节：SK-小金；单位表：心宿工作室567、[ECM]Hamster。
> 隶属：三方同志｜作者交流 QQ 群：528400691。
>
> **本文件是「宾语有哪些类型 / 各类型怎么用 / 生存与资金怎么做」的权威来源。**
> 与 `official_xml_notes.md` 互相补充：那份讲 XML 格式与规范，这份讲宾语类型的**完整覆盖**。

---

---
## 零、【可运行级】完整 XML 代码块（复制进 tmx 即用！）
> 上面各章讲「为什么、怎么用」，这里给「直接能跑的原始代码」。
> **所有代码块均取自成品地图 `随机单位的生存2.0.tmx` 的真实对象，可直接粘进 `<objectgroup name="Triggers">` 里使用。**
> 外层容器长这样（每张地图只有一个）：

```xml
<objectgroup name="Triggers" visible="false">
  <!-- 你的宾语（object）全部写在这里 -->
</objectgroup>
```

### 0.1 map_info（必填且唯一，不写整个触发系统不启动）
```xml
<object id="2000" name="map_info" type="survival" x="0" y="0" width="20" height="20">
  <properties>
    <property name="winCondition" value="NONE"/>
    <property name="survivalWaves" value="+0:15 第一波 - 15 tank,20 mechGun
+2:00 第二波 - 10 heavyTank,15 mechMinigun
+3:00 决战 - 5 mammothTank [win]"/>
  </properties>
</object>
```
> 注：`survivalWaves` 的值里用真实换行，行首一个空格。不写 = 无尽模式。

### 0.2 team_info（玩家初始值，生存必配）
```xml
<object id="2001" name="p1" type="team_info" x="100" y="100" width="20" height="20">
  <properties>
    <property name="credits" value="2000"/>
    <property name="ai" value="survival"/>
    <property name="team" value="0"/>
  </properties>
</object>
```

### 0.3 attack_point（生存刷兵点，name 填名字、type 留空）
```xml
<object id="2002" name="attack_point" x="300" y="300" width="20" height="20"/>
```

### 0.4 unitAdd（刷兵，最常用）
```xml
<object id="2003" name="spawn_tanks" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2(offsetRandomXY=60)"/>
    <property name="team" value="1"/>
    <property name="delay" value="30s"/>
  </properties>
</object>
```

### 0.5 unitDetect（检测覆盖区单位；与 unitAdd 配对做抽签）
```xml
<object id="2004" name="lot_g1_ticket" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/>
    <property name="team" value="-2"/>
    <property name="delay" value="30s"/>
  </properties>
</object>
<object id="2005" name="lot_g1_cell1_det" type="unitDetect" x="120" y="2620" width="40" height="40">
  <properties>
    <property name="unitType" value="mechMissile"/>
    <property name="team" value="-2"/>
    <property name="minUnits" value="1"/>
  </properties>
</object>
```

### 0.6 unitRemove / set_team / rotate / move（配 point）
```xml
<object id="2006" name="clear_area" type="unitRemove" x="400" y="400" width="40" height="40">
  <properties><property name="team" value="-2"/></properties>
</object>
<object id="2007" name="grab_zone" type="set_team" x="400" y="400" width="40" height="40">
  <properties><property name="team" value="0"/></properties>
</object>
<object id="2008" name="turn_north" type="rotate" x="400" y="400" width="20" height="20">
  <properties><property name="dir" value="90"/><property name="team" value="0"/></properties>
</object>
<object id="2009" name="dest_a" type="point" x="900" y="900" width="20" height="20"/>
<object id="2010" name="move_out" type="move" x="400" y="400" width="40" height="40">
  <properties><property name="target" value="dest_a"/><property name="team" value="0"/></properties>
</object>
```

### 0.7 mapText（地图某点显示文字）
```xml
<object id="2011" name="show_title" type="mapText" x="700" y="700" width="20" height="20">
  <properties>
    <property name="text" value="防守这里！"/>
    <property name="textColor" value="#33ff33"/>
    <property name="textSize" value="24"/>
    <property name="textOffsetY" value="-20"/>
  </properties>
</object>
```

### 0.8 changeCredits（改资金，配 unitDetect 做奖励）
```xml
<object id="2012" name="reward_det" type="unitDetect" x="500" y="500" width="60" height="60">
  <properties>
    <property name="minUnits" value="1"/>
    <property name="id" value="reward_det"/>
    <property name="resetActivationAfter" value="true"/>
  </properties>
</object>
<object id="2013" name="reward_add" type="changeCredits" x="500" y="500" width="20" height="20">
  <properties>
    <property name="team" value="0"/>
    <property name="add" value="233"/>
    <property name="activatedBy" value="reward_det"/>
  </properties>
</object>
```

### 0.9 fall / ai_allow_full_use / disable_unit_ai / moveCamera / basic
```xml
<object id="2014" name="airdrop" type="fall" x="300" y="300" width="40" height="40">
  <properties><property name="team" value="0"/></properties>
</object>
<object id="2015" name="let_ai_use" type="ai_allow_full_use" x="300" y="300" width="40" height="40"/>
<object id="2016" name="freeze_ai" type="disable_unit_ai" x="300" y="300" width="40" height="40"/>
<object id="2017" name="cam_here" type="moveCamera" x="300" y="300" width="20" height="20"/>
<object id="2018" name="link_placeholder" type="basic" x="300" y="300" width="20" height="20">
  <properties><property name="alsoActivate" value="spawn_tanks"/></properties>
</object>
```
> 注：`ai_allow_full_use` / `disable_unit_ai` 属“滚木”类型（自定义地图基本用不到，见 **B+ 节**），此处仅为写法示意。

### 0.10 teamTags / teamTagDetect（mod 用）
```xml
<object id="2019" name="add_tag" type="teamTags" x="300" y="300" width="20" height="20">
  <properties><property name="addTeamTags" value="myModTag"/><property name="team" value="0"/></properties>
</object>
<object id="2020" name="detect_tag" type="teamTagDetect" x="300" y="300" width="20" height="20">
  <properties><property name="teamTag" value="myModTag"/></properties>
</object>
```

### 0.11 objective（作胜利条件）
```xml
<object id="2021" name="win_here" type="objective" x="1000" y="1000" width="20" height="20"/>
```
> 再在 map_info 里写 `requiredObjectives="win_here"`，即可把它当胜利条件。

> ⚠️ **通用铁律**：`id` 必须全图唯一、不重复；除 `unitDetect` 外，其他类型不写 `team` 会闪退（全局类如 map_info 除外）。


## 一、宾语三大写法（先分清，别混）

宾语写在 `Triggers` 图层里，靠 **name** 或 **type** 字段决定作用：

| 写法 | 填在哪 | 有哪些 |
|---|---|---|
| **A. 填进「名称」(name)，type 留空** | `name="xxx"` | `map_info`、`camera_start`、`attack_point` |
| **B. 填进「类型」(type)，name 随意** | `type="xxx"` | 见下方完整清单 |
| **C. 填进「属性」(property)** | `<property>` | 各属性的具体值 |

### A 类：填名称的（type 必须空）
1. **`map_info`** —— 地图信息。**每张地图有且只有一个，必填**；没有它整个触发系统不启动。
2. **`camera_start`** —— 初始屏幕位置。属性空；可选 `zoomTo` 改开局视野大小。
3. **`attack_point`** —— 生存模式刷兵点。可建多个；属性空、不用填。以该宾语为原点、半径约 4 格随机出兵。**建太多会出 bug（见第六节）。**

### B 类：填类型的完整清单（主表共 17 类，name 随意）

> 另有两类「滚木」类型（`ai_allow_full_use` / `disable_unit_ai`）已移到下方 **B+ 节**；一类补充类型 `multiTrigger` 见 **B++ 节**。

| # | 类型 | 作用 | 必填/专属属性 |
|---|---|---|---|
| 1 | `team_info` | 设置玩家初始值（资金/盟友/AI 行为） | `credits`/`disabledAI`/`lockAiDifficulty`/`ai`/`allyGroup`/`basicAI` |
| 2 | `unitAdd` | 刷兵（也可刷聊天区系统文字） | `spawnUnits`（必填），`team` 必填 |
| 3 | `unitRemove` | 删除单位（不能指定特定单位） | 同 unitAdd 用法 |
| 4 | `unitDetect` | 检测覆盖区内单位是否满足条件 | 见第四节条件表 |
| 5 | `mapText` | 在地图某点显示文本 | `text`/`textColor`/`textSize`/`textOffsetX`/`textOffsetY`/`style`/`text_lang` |
| 6 | `camera_pan` | 更改玩家屏幕显示区域 | `index`（**注意：不可用于自定义地图**） |
| 7 | `objective` | 自身无作用，作 `requiredObjectives` 的胜利条件（被激活即胜利） | — |
| 8 | `fall` | 开局在该宾语覆盖区空投单位（对部分单位无效） | — |
| 9 | `rotate` | 改变单位旋转角度 | `dir`（0–360.0，顺时针） |
| 10 | `move` | 指定单位移动（不含建筑） | `target`（=目的 point 的 name）、`unload` |
| 11 | `point` | 移动目的地，与 move 连用；目的地=宾语所在位置 | 属性空 |
| 12 | `set_team` | 设置覆盖区内单位所属队伍 | `team` |
| 13 | `moveCamera` | 强制把屏幕视野移到指定位置 | 通用属性；**不可用 `spawnUnits`/`team`** |
| 14 | `teamTags` | 编辑（添加/删除）队伍标签，用于 mod | `addTeamTags`/`removeTeamTags` |
| 15 | `teamTagDetect` | 检测队伍标签，用于 mod | `teamTag` |
| 16 | `basic` | 自身无作用，做链接激活**占位符**（最常用） | 通用属性 |
| 17 | `changeCredits` | **更改玩家资金** | `set`/`add`（见第三节） |

---

### B+ 节 · 不常用 / 自定义地图基本用不到（“滚木”类型，单列以免误导）

> 实测结论：**这两类对自定义地图几乎无用**，仅在特定脚本/mod 场景偶有出现。已从主表移出，避免新手误以为“常用必配”。

| 类型 | 作用 | 备注 |
|---|---|---|
| `ai_allow_full_use` | 允许 AI 充分使用覆盖区内单位 | 区域型（靠 x/y/width/height 圈区），属性空；自定义地图基本用不上 |
| `disable_unit_ai` | 禁止 AI 使用覆盖区内单位移动（不禁工厂） | 区域型，属性空；同上 |

---

### B++ 节 · 补充 / 进阶类型（主表未列但 RW 真实存在）

| 类型 | 作用 | 备注 |
|---|---|---|
| `multiTrigger` | **检测 + 动作合一**：一个对象同时既是检测器（如 `unitDetect` 条件）又能执行动作（如 `unitAdd`/`move`/`changeCredits`），条件满足即执行 | RW 真实存在且常用。与“`unitDetect` + `unitAdd` 分开配对写”是两种等价写法，按需选其一。仍须遵守通用属性与 `team` 铁律（不写 `team` 会闪退） |

> 注：`multiTrigger` 与 `basic` 不同——`basic` 只是占位/旁白、本身不检测；`multiTrigger` 本身带检测条件并执行动作。

> ⚠️ **命名提示（新旧来源差异）**：
> - 2.6 教程写作 **`camera_pan`**（自定义地图无效）与 **`moveCamera`**（强制移屏）是两个不同东西。
> - 旧 XML 规范只提了 `moveCamera`。**稳妥做法：自定义地图一律用 `moveCamera`；`camera_pan` 仅在战役/mod 场景考虑。**

---

## 二、生存模式地图制作（完整流程）

### 2.1 一张合格生存地图至少要有三个宾语
1. **`map_info`** —— 至少写 `type=survival`，`winCondition` 可写 `NONE`（也可用 `requiredObjectives` 配合 `objective`）。
2. **`team_info`** —— 设置玩家初始资金、AI 行为等。想让它像标准生存一样主动送兵：加 `ai=survival`。
3. **`attack_point`**（一个或多个）—— 生存刷兵点，`name` 填 `attack_point` 之类，`type` 留空。

### 2.2 出兵波次：`survivalWaves`（写在 map_info 里）
格式（每波一行，行首一个空格）：
```
+分钟数:秒数 提示文本 - 数量 单位名,数量 单位名...
```
- 先写 `+`，紧跟与**上一波**的间隔；空一格 → 提示文本（屏幕上显示）；空一格 → `-`；再写 `数量 单位名`。
- 可写多种单位，**英文逗号**分隔；也可不写单位（即不出兵）。
- 例：`+0:15 第一波 - 15 tank,20 mechGun`
- **最后一波末尾加 `[win]` 让游戏判定胜利**（如 `+3:00 决战 - 5 mammothTank [win]`）。
- **不写 survivalWaves** → 无尽模式，系统默认出兵。

### 2.3 AI 更主动送兵
`team_info` 加 `ai=survival`：建造者等也会被拿去送兵；且**对方没有对应可攻击单位时该单位不会移动**（如你没空中单位时对方拦截机不会来）。

### 2.4 常见坑
- **刷兵点太多**：最后一个出兵点可能不出兵 → 多加一个出兵点。
- `attack_point` 属性**留空**，别乱填。
- 单位名严格按单位表大小写（见第五节）。

---

## 三、资金更改教程（changeCredits，用户重点缺口）

`type="changeCredits"`，用来给某玩家加钱/设钱。

### 3.1 核心属性
| 属性 | 作用 | 说明 |
|---|---|---|
| `set` | **直接设置**队伍资金 | 可为负数；数值过大**无效**；1.14 会报错但可运行，1.15 修复 |
| `add` | **添加**资金（加/减） | 可为负数；数值过大无效；1.14 报错且**无效**（需第三方触发），1.15 修复 |

搭配通用属性 `team`（哪个玩家）、`activatedBy`（触发来源）、`warmup`（延迟）。

### 3.2 实战实例（加钱）
```
unitDetect（minUnits=1 + id + resetActivationAfter）
   → changeCredits（team=0, add=233, activatedBy=<unitDetect 的 id>）
```
效果：检测到单位后，给玩家加 233$。

### 3.3 伪无限资金
`set` 搭配 `resetActivationAfter`，可做出「伪无限资金」效果。

### 3.4 版本提示
1.14 的 `add` 必须由第三方触发（`id`/`activatedBy` 等）；1.15 已修复，可正常用。

---

## 四、unitDetect 完整条件清单

填在 `unitDetect` 里，值为 `true`/`false`（除注明外）：

| 属性 | 含义 |
|---|---|
| `unitType` | 指定单位类型（值填单位名）才满足 |
| `onlyIdle` | 只有闲置单位 |
| `onlyBuildings` | 只有建筑物 |
| `onlyMainBuildings` | 只有主要建筑（能造东西的工厂） |
| `onlyEmptyQueue` | 只有空队列（工厂不在生产时） |
| `onlyBuilders` | 只有建造者 |
| `onlyOnResourcePool` | 只有在矿坑上（矿坑上有采集器时） |
| `onlyAttack` | 只有攻击性单位 |
| `onlyAttackAir` | 只有只攻击空军的单位 |
| `onlyTechLevel` | 有符合该科技等级的单位（**值填数字**） |
| `includeIncomplete` | 有未建造完成的单位 |
| `minUnits` | 触发所需**最少** x 个单位（值填数字） |
| `maxUnits` | 触发**最多**不超过 x 个单位（值填数字） |
| `onlyWithTag` | 有特定标签的单位 |

---

## 五、单位表要点（严格大小写）

**唯一标准：单位名必须与游戏内部完全一致。** 常见规则：
- 单单词全小写：`tank`、`scout`、`builder`、`bomber`、`gunBoat`
- 双单词第二个首字母大写：`heavyTank`、`hoverTank`、`mechFactory`、`laserTank`、`mammothTank`、`plasmaTank`
- 特殊：
  - 带下划线老单位：`c_tank`、`c_artillery`、`wall_v`、`crystalResource`
  - 首字母缩写全小写：`aaBeamGunship`、`spyDrone`
  - 等级 T3 大写：`bugMeleeT31`
  - 部署/变形状态是**另一个单位名**：`mechBunkerDeployed`、`nautilusSubmarine`、`experimentalGunshipLanded`、`mechFlyingLanded`
  - 二级工厂等**无独立名**时，用 `spawnUnits` 的 `techLevel` 生成。
- **注意**：教程单位表里**划横线的为 1.15 版本新增单位**；照抄时以教程正文（无横线的文本形式）为准。

### 5.1 常用单位速查（按教程单位表，严格照抄）
> 一级工厂内部名教程给了；**二级工厂原文未给内部名**（教程原话："有一些二级建筑没有对应名称，如二级空军工厂，添加时需用 `spawnUnits` 附加属性的科技等级 `techLevel` 来生成"）。下表二级项仅列单位名，工厂请用 `techLevel` 生成。
- **陆军工厂** `landFactory`：`scout`、`builder`、`tank`、`c_tank`(老版坦克)、`hoverTank`、`c_artillery`；二级：`heavyTank`、`heavyhoverTank`(重型气垫坦克)、`plasmaTank`、`heavyArtillery`、`mammothTank`、`laserTank`、`missileTank`、`combatEngineer`
- **机械工厂** `mechFactory`：`mechGun`、`mechMissile`、`mechArtillery`、`mechBunker`、`mechBunkerDeployed`(部署态)；二级：`mechMinigun`、`mechEngineer`、`mechLaser`、`mechLightning`、`mechHeavyMissile`、`mechFlame`
- **空军基地** `airFactory`：`lightGunship`、`c_interceptor`(拦截机)、`helicopter`；二级：`gunShip`、`heavyInterceptor`、`dropship`、`amphibiousjet`、`bomber`、`missileAirship`、`aaBeamGunship`、`spyDrone`
- **海军工厂** `seaFactory`：`gunBoat`、`builderShip`、`hovercraft`、`missileship`、`attackSubmarine`、`battleShip`；二级：`heavyBattleship`、`heavySub`、`heavyMissileShip`、`nautilusSubmarineSurface`(鹦鹉螺号)、`nautilusSubmarine`(鹦鹉螺潜水态)、`experiementalCarrier`(航空母舰，⚠️ 教程原文即如此拼写，非 `experimentalCarrier`)、`heavyAAShip`
- **实验工厂** `experimentalLandFactory`：`fireBee`、`experimentalTank`、`experimentalHoverTank`、`experimentalDropship`、`experimentalSpider`
- **建筑**：`commandCenter`、`extractor`/`extractorT2`/`extractorT3`、`extractorT3_reinforced`、`extractorT3_overclocked`、`fabricator`/`fabricatorT2`/`fabricatorT3`、`turret`/`turretT2`/`turretT3`、`turret_flamethrower`、`turret_artillery`、`c_turret_t2_artillery`、`c_turret_t1_lightning`、`c_turret_t2_lightning`（2 级电击塔，⚠️ 教程原文误写成 `c_turret_t2_lightnin` 漏了 g，游戏内实际认标准拼写，以 `lightning` 为准）、`antiAirTurret`、`c_antiAirTurretT2`、`c_antiAirTurretT3`、`antiAirTurretFlak`、`repairbay`、`laserDefence`、`outpostT1`/`outpostT2`、`laboratory`、`nukeLauncherC`、`antiNukeLauncherC`、`crystalResource`/`crystal_mid`、`creditsCrates`
- **虫族单位**：`bugNest`、`bugSpore`、`bugFly`、`bugMelee`、`bugWasp`、`bugPickup`、`bugBee`、`bugRanged`、`bugRangedT2`
- **虫族建筑**：`bugTurret`、`bugExtractor`/`bugExtractorT2`、`bugGenerator`/`bugGeneratorT2`
- **虫族隐藏单位**：`ladybug`、`bugMeleeSmall`、`bugMeleeLarge`、`bugMeleeT31`、`bugGeneratorN`、`bugGeneratorNT2`

### 5.2 隐藏单位（正版隐藏/作者专用，做特殊地图很有用）
- **隐藏单位**：`robotCrab`（机械螃蟹）、`robotCrabWater`（水中机械螃蟹）、`megaTank`（超级坦克）、`tankDestroyer`（坦克杀手）、`experimentalGunship`（悬浮基地）、`experimentalGunshipLanded`、`mechFlyingTakeoff`（飞行机甲）、`mechFlyingLanded`、`wall_v`（城墙）、`supplyDepot`（补给站）、`modularSpider`（模块化蜘蛛）、`spreadingFire`（永恒之火）、`flare_10s`（信号烟）、`fogRevealer`（迷雾探测器）、`missing`（错误单位）、`zoneMarker`（安全区/毒圈白圈）、`damagingBorder`（轰炸区/毒区伤害）、`editorOrBuilder`（沙盒建造者）、`tree`（树，Items 层用）、`custom_tank`（远古小坦）、`example_faction_picker`（阵营选择器）
- **老版遗留**：`nukeLaucher`（老版核弹发射器）、`antiNukeLaucher`（老版核弹拦截器）、`crystalResource`（老版水晶，可设队伍、可直接被攻击）、`dummyNonUnitWithTeam`（作者调试单位）、`showFog`（迷雾清除，Units/Items 层均可放）

### 5.3 模块化蜘蛛模块（`modularSpider_*`，共 17 个）
- 空模块：`modularSpider_emptySlot`
- 反核：`modularSpider_antinuke`
- 防空炮塔：`modularSpider_antiair` / `modularSpider_antiairT2`
- 高射炮：`modularSpider_antiairFlak`
- 火炮：`modularSpider_artillery`
- 资源制造：`modularSpider_fabricator` / `modularSpider_fabricatorT2`
- 机枪：`modularSpider_gunturret` / `modularSpider_gunturretT2`
- 激光防御：`modularSpider_laserdefense`
- 护盾增幅：`modularSpider_shieldGen`
- 等离子炮：`modularSpider_smallgunturret` / `modularSpider_smallgunturretT2`
- 闪电炮塔：`modularSpider_lightning`
- 速度增幅：`modularSpider_speed`
- 传送：`modularSpider_blink`

---

## 六、常见 bug 与排查（2.6 教程补充）

1. **宾语不触发且无报错** → 检查是否**忘写 `map_info`**。
2. **报错找不到问题** → 多半是**拼写错**（尤其漏 s，如 `spawnUnits`/`units`）。
3. **报错「找不到属性」** → 地图里有**空白宾语**，找到删掉。
4. **生存刷兵点太多** → 最后一个不出兵，多加一个出兵点。
5. **地图文件变 0B 打不开** → 千万别点 nottiled 左边的「开始游戏」按钮。
6. **概率不稳定**（如 0.25 却 10 次中 9 次）→ 铁锈概率算法特殊，只能自己调。
7. **宾语过多时部分失效** → 删掉重写（**别复制粘贴宾语**，复制件有概率失效）。
8. **随机生成并不随机** → 无解，是游戏本身问题。

---

## 七、通用属性完整清单（大多数宾语适用）

| 属性 | 作用 |
|---|---|
| `team` | 限定触发玩家；`-2` 敌 / `-1` 中立 / `0` 玩家1 / `1` 玩家2 …。unitDetect 不写=全玩家通用；**其他类型不写会闪退**（全局类除外） |
| `warmup` | 触发后延迟 N 产生效果（`1000ms`=1s，可写 `s`） |
| `delay` | 开局后延迟 N 才触发（与 warmup 相近，一般可互换） |
| `repeatDelay` | 触发后每隔 N 重复触发（不写则只触发一次） |
| `resetActivationAfter` | 触发后需**重新满足条件**才再触发 |
| `globalMessage` | 左上角聊天区文字 |
| `globalMessage_delayPerChar` | 逐字显示间隔（可写 `slow`） |
| `globalMessage_textColor` | 文字颜色 |
| `debugMessage` | 沙盒 debug 模式显示的调试文本 |
| `alsoActivate` | 本宾语被激活时，同时激活 id 相同的宾语 |
| `activatedBy` | 需**任意一个**来源被触发即触发（值=来源 name）。**语义关键**：只需任一来源激活 |
| `deactivatedBy` | 指定来源被触发时**禁止**触发 |
| `allToActivate` | 需**所有**来源都激活才触发（true/false）；**必须搭配 `activatedBy` 一起写**（否则不生效） |
| `id` | 定义本宾语 id（供 alsoActivate/activatedBy 引用） |
| `activateIds` | 类 alsoActivate |
| `whenActivatedIds` | 类 activatedBy |
| `showOnMap` | 小地图事件提示（true/false） |

> `delay` vs `warmup`、`repeatDelay` vs `resetActivationAfter` 的区别见 `official_xml_notes.md` 第 6.4 节。

---

## 八、spawnUnits 附加属性完整清单

格式：`单位名*数量(属性=值,属性=值)` —— 括号紧贴数量、无空格。

| 属性 | 作用 |
|---|---|
| `neutralTeam` | 变中立单位（true/false） |
| `spawnChance` | 生成概率 0–1（铁锈概率不稳定） |
| `maxSpawnLimit` | 生成数量上限（随机取 0~该值） |
| `techLevel` | 科技等级；超上限会降到 1 级；对改名升级单位无效（如 mechFactory→mechFactoryT2）；也可表缩圈范围（1 级=5 格） |
| `gridAlign` | 网格对齐（true/false） |
| `skipIfOverlapping` | 单位不适配地形则跳过（如 seaFactory 不能放陆地/岩浆） |
| `falling` | 从天而降（true/false，对部分单位无效） |
| `offsetX` / `offsetY` | X/Y 轴偏移 |
| `offsetRandomX` / `offsetRandomY` | X/Y 轴随机偏移 |
| `offsetRandomXY` | 2D 范围随机偏移 |
| `offsetHeight` | 生成高度（可做地下防空） |
| `offsetDir` | 生成方向（0–360） |
| `offsetRandomDir` | 生成方向上随机（0–360） |

---

## 九、其他类型属性速查

- **mapText**：`text`、`textColor`（`#33ff33` 或 `blue`/`red`/`cyan`）、`textSize`、`textOffsetX`/`textOffsetY`（20=一格）、`style=arrow`、`text_lang`（多语言）。
- **move**：`target`（=目的 point 的 name）、`unload`。
- **rotate**：`dir`（0–360.0）。
- **teamTags**：`addTeamTags`、`removeTeamTags`；**teamTagDetect**：`teamTag`。
- **team_info**：`credits`、`disabledAI`、`lockAiDifficulty`（-2 VeryEasy ~ 3 Impossible，过大崩溃）、`ai=survival`、`allyGroup`（同组互为队友）、`basicAI`。

---

> 内容整理自《铁锈超级详细的触发层宾语教程（图文 v2.6）》。
> 原作者：斐比寻常W'213（QQ 2441054858）｜资金章节：SK-小金｜单位表：心宿工作室567、[ECM]Hamster。
> 本 Skill 署名：三方同志｜作者交流 QQ 群：528400691。
