# RW .tmx GID 与触发字段对照（实战核对版）

## A. GID 分配（单文件内联图集）

本 Skill 把"地面层整合"图集与 `misc`(水晶/树)合并为**一个内联图集**，`firstgid=1`：

| 区间 | 内容 | tile_id 范围 | 备注 |
|---|---|---|---|
| 地面/装饰 | 地面层整合.tsx 全部 tile | 0 .. 1079 (1080 格) | 含四角 autotile 地形 + 山/泥坑/岩石装饰 |
| 起步矿(被动收入) | misc 的 `id=4` | **1084** | 带 `res_pool` → 资源矿（GID=1+1084=1085），用于每队出生岛起步矿 |
| 合并的树 | misc 的 `id=9,10,...` | 1089,1090,... | 带 `unit="tree"`（装饰，不可采） |

- `COMBED_COUNT = 1080`（地面图集格数）
- `MERGED_COUNT = 1098`（合并后总格数 = 1080 + 18）
- 地图层存 GID = `firstgid(1) + tile_id`。起步矿在 Items 层写作 GID **1085**。
- 起步矿识别靠 tile 属性 `<property name="res_pool" value=""/>`，**不靠图集名**。
- ⚠ **中岛「水晶」不是这里的水晶矿**：它是单位 `crystalResource`（单位表第 93 行），由 `UnitObjects` 对象组刷出（属性 `team="-1"` 中立 + `unit="crystalResource"`），**不在地图层、不带 res_pool**。详见 SKILL.md 坑 12。

tile 尺寸：图集与地图均为 `tilewidth=tileheight=20`（列数 36 → png 宽 720；1098 格 → 31 行 → png 高 620）。

## B. 图层结构

| 图层名 | 内容 | 压缩 |
|---|---|---|
| Ground | 地形（草/沙/水/山/泥坑） | base64 + gzip |
| Decorations | 岩石/枯木装饰 | base64 + gzip |
| Items | 起步矿（res_pool，GID=1085，每队出生岛 2 个） | base64 + gzip |
| Units | 通常为空（初始单位不靠该图层，而靠 `UnitObjects` 对象组直接刷出） | base64 + gzip |
| UnitObjects(objectgroup) | **初始单位/建筑**：每队 1 主基地 + 2 工程兵 + **中岛 4 个 crystalResource 水晶单位(中立)**（直接刷出，开局即存在） | — |
| Triggers(objectgroup) | 保留 `map_info` + `camera_start`；可选 **城夺触发器**（每队一对 `unitDetect` 死亡检测 + `unitAdd` 刷中立总部，见下）；`team_info`、`unitDetect` 占点广播已刻意移除（见下） | — |

## C. 触发对象字段（objectgroup 内 `<object type=...>`）

### map_info（元数据，type 可留空）
| 属性 | 值 | 说明 |
|---|---|---|
| type | skirmish | 遭遇战模式 |
| winCondition | mainBuilings | 拆光对手生产建筑即胜（可选 none / requiredObjectives） |
| fog | los | 战争迷雾 |
| introText | 多行文本 | 开局说明（建议含：地图名/玩法简介 + **Q群** + **作者**） |

### team_info（❌ 本图不用！多人模式无效）
`{team: i, credits: 1500, allyGroup: i}`，坐标 = 出生岛像素位置。
> **坑**：`team_info` 在**多人模式**下会被房间资金配置**覆盖**，等于无效（`credits`/`allyGroup` 都来自建房设置），仅在单人模式起作用。做多人地图时它是累赘，直接不写即可。

### unitDetect（检测器，type="unitDetect"，⚠️ 本图用它做城夺、不再做占点广播）
 RW 1.15 检测器内部为 `trigger_unitDetect`；满足 `minUnits ≤ 区域内单位数 ≤ maxUnits`（按 `unitType` 过滤）时触发，并通过 `activatedBy`（目标对象 name）激活别的触发器。

| 属性 | 值 | 说明 |
|---|---|---|
| unitType | commandCenter / builder / … | 只统计该单位类型（城夺死亡检测用 `commandCenter`） |
| minUnits | 1 | 区域内该单位 ≥1 时触发（城夺"玩家靠近"用这个） |
| maxUnits | 0 | 区域内该单位 ≤0（即归零）时触发（**城夺死亡检测用这个**：总部被打爆） |
| team | i（可选） | 只统计第 i 队的单位；不写则统计所有队 |
| range / x,y,width,height | 像素矩形 | 检测区（城夺取覆盖总部的 80×80） |
| resetActivationAfter | 1440 | 再次触发前的冷却（tick/秒）。事件播报类用 `99999` 防反复刷屏 |
| globalMessage | 文本 | **全屏播报**（归零/触发瞬间播一次）。仅用于单边固定事件（某城/首都/古巴沦陷），不要用于"多队同占"广播（见 SKILL.md 坑 6/坑 18） |
| activatedBy | 目标对象 name（逗号分隔可链式） | 本检测器触发时，去激活名为该值的对象。**逗号分隔可一次激活多个**（如古巴沦陷 → 同时激活"加钱"+"刷机"+"刷核弹井"），实现事件→多动作。name 必须与目标对象 `name` 严格一致 |

> **城夺死亡检测用法**（合法）：`<object type="unitDetect" maxUnits=0 unitType=commandCenter …>`，区域内 commandCenter 归零→触发→激活 `unitAdd` 刷中立总部。
> **占点广播（已移除）**：`minUnits=1 + onlyBuildings + globalMessage="X队占领了中岛"` 这种全屏广播本图刻意移除——多人混战时多队可能**同时**在中岛立塔，会对每个满足条件的队各播一次，出现「队伍 3 和队伍 5 都占领了中岛」矛盾消息。占点价值改由经济要地（中岛 4 水晶＝唯一富矿）体现。

### unitAdd（中局刷中立总部用 ✅；开局初始单位 ❌ 见坑 9）
 RW 1.15 动作内部为 `event_unitAdd`。**合法用途：城夺**——总部被毁后刷一个 `team=-1` 的中立总部，由玩家靠近 native 占领（见下）。**非法用途：开局刷初始主基地**——它是"触发"，开局第一帧胜负判定先于触发执行，单位未刷出就被判负；且仅刷 `builder` 不刷主基地，`mainBuilings` 下每队因"无主建筑"立刻判负（坑 9）。

| 属性 | 值 | 说明 |
|---|---|---|
| spawnUnits | commandCenter / … | 刷出的单位内部名（城夺=`commandCenter`） |
| team | -1 | 刷出的队伍；`-1`=中立，可被任意靠近玩家占领（城夺核心） |
| activatedBy | 死亡检测对象 name | 被该检测器激活时才刷（城夺里挂在 `unitDetect` 上，避免开局误刷） |
| resetActivationAfter | 1440 | 冷却 |
| x,y | 像素 | 刷出位置（=总部中心） |

> ⚠️ **权威结论（比对 RW 1.15 本体 `classes.dex`）**：RW 触发器动作类型只有 `event_unitAdd` / `event_unitRemove` / `event_move` / `event_changeCredits` / `event_teamTags`（检测器 `trigger_unitDetect` / `trigger_teamTagDetect` / `trigger_basic`）。**不存在 `unitSet` 这个触发类型**——`宾语复制器` apk 里那个 `unitSet` 只是作者自己的 Kotlin 类名，RW 不认。所以"按队转化"靠 **team=-1 建筑的 native 占领**完成，不要写 `type="unitSet"`。

### changeCredits（✅ 地图内"给钱/加钱"唯一可靠手段，多人房不可覆盖）
 RW 1.15 动作内部为 `event_changeCredits`。**地图内经济（启动资金、周期经济、事件奖金）只能用这个**，不能用 `startingCredits`/`team_info`（多人局被房主建房设置覆盖，等于无效，见 SKILL.md 坑 15）。

| 属性 | 值 | 说明 |
|---|---|---|
| team | i | 给第 i 队加钱（古巴图：0=美，1=苏） |
| credits | 数值 | 加/设的资金量 |
| add | "true" | **"true"=在现有资金上追加（推荐）**；不写或 false=把资金设成该值（慎用，会清零已有资金） |
| resetActivationAfter | 99999 / 周期帧 | 冷却。开局注资用 `99999`（只触发一次）；周期经济用周期帧（如 900≈15秒） |
| x,y | 像素 | 任意（changeCredits 是全局动作，不依赖位置，常写 0,0） |

> 常见组合：① `unitDetect(主建筑存在, minUnits=1)` → `activatedBy` 激活 `changeCredits(add=true, credits=15000)` 做**开局注资**（核弹造价 11000，够立刻造）；② `unitDetect(resetActivationAfter=900)` 周期触发 → 激活 `changeCredits(add=true, credits=1500)` 做**持续经济**；③ 事件链（如古巴沦陷）`activatedBy` 同时激活 `changeCredits(add=true, credits=12000)` 给胜方追加资金。

### UnitObjects（✅ 初始单位/建筑，必须用这个）
对象组 `name="UnitObjects"`，组内每个 `<object>` 用属性描述单位（对象的 `type`/`name` 不用填）：
- `team`：队伍号（0=队伍1绿，1=队伍2红…；-1=中立，-2=敌对）
- `unit`：单位**内部名**（写模组里 `name` 字段，不是 displaytext）

```xml
<objectgroup name="UnitObjects">
  <object id="35" x="1600" y="300" width="20" height="20">
    <properties>
      <property name="team" value="0"/>
      <property name="unit" value="commandCenter"/>   <!-- 主基地，满足 mainBuilings -->
    </properties>
  </object>
  <object id="36" x="1660" y="300" width="20" height="20">
    <properties>
      <property name="team" value="0"/>
      <property name="unit" value="builder"/>          <!-- 工程兵 -->
    </properties>
  </object>
</objectgroup>
```
> 每队建议 `commandCenter*1 + builder*2`，坐标=出生岛像素（`col*20,row*20`），单位间留 1 格间距避免重叠/卡位。

**脚本事件图常用单位内部名（详见 `references/单位表_1.15.txt`）**：
| 内部名 | 兵种 | 注意 |
|---|---|---|
| `commandCenter` | 指挥中心（主基地） | 满足 `mainBuilings`；陆地建筑 |
| `seaFactory` | 海军工厂 | **水上主建筑**，苏军主基地用它保证 `mainBuilings` 不误判全灭 |
| `extractor` | 资源提取器 | 资源点单位（每城 1 个 = 该城经济） |
| `nukeLauncherC` | 核弹发射井 | **陆地建筑**，落点必须吸附到陆地（落水=摆设，见 SKILL.md 坑 16） |
| `creditsCrates` | 中立钱箱 | **地面单位**，放纯水不显示；吸附到海岸沙地保证可见（坑 16） |
| `experiementalCarrier` | 航母 | ⚠️ RW 自带拼写是 `experiemental`（少个 e），照抄 |
| `battleShip` / `heavyBattleship` / `missileship` | 战列/重战列/导弹舰 | 水面舰，周期增援注意雪崩（坑 17） |
| `attackSubmarine` | 攻击潜艇 | 水面单位 |
| `c_interceptor` / `bomber` | 拦截机（小飞机）/轰炸机 | 空中单位；"刷小飞机"用 `c_interceptor` |
| `builderShip` | 海上建造者 | 苏军可重建工程的船 |

### camera_start
`{ }`，坐标 = 地图中心像素（`cx*20, cy*20`）。

## D. 常见错误码 ↔ 根因

| 报错 | 根因 | 修复 |
|---|---|---|
| `Could not find unit type: core` | 触发用了非法单位 `core` | 改成 `builder` |
| `Unable to load or parse sourced tileset: tilesets/xxx.tsx` | 地图带外部 `.tsx` 引用，RW 去内部 `tilesets/` 找 | 内联图集 + 内嵌图片，消除 `source=` |
| 地图全灰/无矿 | 水晶 tile 缺 `res_pool` 或 GID 越界 | 合并时保留 `res_pool`，校验 GID≤tilecount |
| 单位不落在出生岛 / 占点不触发 | 坐标乘错 tile 尺寸（用了 32） | 统一乘地图 `tilewidth`（本例 20） |
| 一开局（0 秒）就判某队失败 / 直接结束 | 初始单位用了 `unitAdd` 触发，或 `mainBuilings` 下没有主基地 | 改用 `UnitObjects` 对象组 `unit` 属性刷 `commandCenter`+`builder`，开局即存在 |
| 沙岸/沙桥边缘贴着深蓝（海/洋）硬切、无过渡 | 沙直接覆盖到海/洋上（图集无 沙↔海、沙↔洋 过渡块） | 沙带两侧垫缓冲带：沙→浅滩→水→(洋降级为海)，链条 沙→浅滩→水→海→洋 全有过渡块；见 SKILL.md 坑 10 |
| 水里漂浮孤立浅滩碎斑（噪声甩出的脏点） | 缓冲带浅滩被多频噪声甩进开阔水，离沙带 2 格外 | 地形生成后做后处理：浅滩且 Chebyshev 2 内无沙→降级为水；见坑 11。用 `verify.py` 自检碎斑=0 |
| 中岛看不到"水晶"、或水晶无法抢占/回收 | 把水晶当 res_pool 矿坑放进 Items 层（只是普通矿，不是玩法单位） | 中岛「水晶」是单位 `crystalResource`，用 `UnitObjects` 刷（属性 `team="-1"` 中立 + `unit="crystalResource"`）；见 SKILL.md 坑 12 |
| 核弹买不起 / 玩家开局没钱 | 用 `startingCredits` 或 `team_info` 设资金——多人局被房主建房设置**覆盖**，等于没给 | 改用 `changeCredits` 触发器（地图逻辑不可覆盖）：`unitDetect(主建筑存在)` → `activatedBy` 激活 `changeCredits(add="true", credits=15000)` 做开局注资；见 SKILL.md 坑 15 |
| 核弹发射井/钱箱看不到、或核弹井无法造核弹 | `nukeLauncherC`/`creditsCrates` 是**地面单位**，坐标落在纯水（水/海/洋）上不显示 | 落点用 `snap_land()` 吸附到最近草/沙；核弹井必须陆地（落水=摆设）；见 SKILL.md 坑 16 |
| 苏军后期无限堆兵、碾压玩家 | 周期增援 `unitAdd` 的 `resetActivationAfter` 太小（<30秒），且无"主建筑存在"gate | 放大周期（强单位 50~90 秒级=3000~5400帧），并用 `unitDetect(主建筑存在)` 当 gate，主建筑被毁即停；见 SKILL.md 坑 17 |
| 事件播报反复刷屏 / 多队矛盾消息 | `unitDetect` + `globalMessage` 用于"多队同占"类广播（每队各播一次） | 播报只用于单边固定事件（某城/首都/古巴沦陷，`maxUnits=0`），`resetActivationAfter=99999`；多队占点广播已移除（坑 6/坑 18） |
