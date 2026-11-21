# 天雷特效（非比寻常式：高度欺骗 + 删除）

## 一、这是什么 / 出处

- **非比寻常**（知名《铁锈战争》自定义地图作者）在国家 / 战争题材地图里常用的「天上霹雷」演出特效：屏幕里一道高耸单位的剪影从天垂落、又骤然消失，观感像一道闪电 / 霹雷劈下。
- **纯演出**：无伤害、无经济、不影响胜负，可安全叠加多个。常用于「神迹降临」「轰炸前奏」「区域警示」「剧本过场」等氛围渲染。

## 二、原理（RW 1.15 引擎依据，已核对）

1. 单位有**生成高度**属性 `offsetHeight`（见 `trigger_objects_v26.md` 第八节：「生成高度（可做地下防空）」）。把它设成很大的值（如 1000~2000），单位就出生在对应高度的高空。
2. RW 引擎对悬浮单位有**重力自动校正**：`movement.heightChangeRate`、`movement.fallingAcceleration` / `fallingAccelerationDead`（见官方 1.14/Mod 特性文档）。即：单位不会永久漂在高空，引擎会把它「拽」回地面真实高度——这就是用户说的**「游戏自动矫正真实高度」**。
3. 在它**落地（矫正完成）之前**用 `unitRemove` 把它删掉 → 屏幕里只短暂出现「高空垂落的单位 + 地面投影」再凭空消失 = 霹雷。

> 一句话记忆：**架高 → 引擎重力往下拽 → 落地前删掉 → 一道霹雷垂落又消失。**

## 三、配方（直接抄）

两种写法，推荐 **写法 A**（全部用触发器，时序最稳、可控）。

### 写法 A：Triggers 里 `unitAdd` 刷 + `unitRemove` 删（推荐）

```xml
<!-- 1) 开局刷一个高空炮塔（中立，纯演出） -->
<object id="9001" name="天雷刷_1" type="unitAdd" x="600" y="160" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="turret*1(falling=true,offsetHeight=1400)"/>
    <property name="team" value="-1"/>
    <property name="resetActivationAfter" value="99999"/>
  </properties>
</object>

<!-- 2) 在它落地前删掉（delay 让它先在天上露脸再消失） -->
<object id="9002" name="天雷删_1" type="unitRemove" x="600" y="160" width="40" height="40">
  <properties>
    <property name="spawnUnits" value="turret"/>
    <property name="team" value="-1"/>
    <property name="delay" value="40"/>
    <property name="resetActivationAfter" value="99999"/>
  </properties>
</object>
```

- `unitAdd` 无 `activatedBy` → 开局即刷；`resetActivationAfter=99999` 保证只刷一次。
- `unitRemove` 也无 `activatedBy` → 开局即激活，靠 `delay=40`（约 0.66 秒）延后执行；`spawnUnits="turret"` + `team=-1` 精确只删这只高空炮塔，`resetActivationAfter=99999` 一次。

### 写法 B：UnitObjects 直接摆 + Triggers 删

把单位直接放进 `UnitObjects`（属性 `unit=turret`、`team=-1`、`offsetHeight=1400`），再配一个 `unitRemove` 触发器（同写法 A 第 2 步）删除。

- 区别：B 的单位在地图编辑器里可见、会被存档；A 的单位只在运行时出现。演出类推荐 A。

## 四、调参（决定像不像霹雷）

| 参数 | 作用 | 建议值 |
|---|---|---|
| `offsetHeight` | 架多高；越大「柱子」越高、下落越久越明显 | 800~2000（<300 几乎看不出） |
| `delay`（unitRemove） | 「露脸时长」；越大越像一道霹雷划过 | 40~90 帧（0.66~1.5 秒） |
| 单位选型 | **高、窄、竖长**最出效果 | 炮塔 / 建筑（扁平单位如坦克/船效果差） |
| 多道雷 | 多放几组坐标即可 | — |
| 循环劈雷 | `unitAdd` 与 `unitRemove` 的 `resetActivationAfter` 设同一周期（如 600≈10 秒一道），且 `delay` 必须小于该周期 | — |

## 五、坑 / 注意

- ⚠️ **`unitRemove` 删的是覆盖区内所有匹配单位，不能指定单个**。务必把天雷点放在没有友军 / 敌军单位的空地或海上；并用 `spawnUnits` 填具体类型（如 `turret`）把误删范围缩到最小。
- `falling=true` 对**部分单位无效**（见 `trigger_objects_v26.md` 第八节），建筑类大多可用；即便无效，`offsetHeight` 仍会被重力校正拽下来，效果一致——所以 `falling` 是锦上添花，`offsetHeight` 才是核心。
- 纯演出，无伤害、无经济，可放心叠加。
- 不要在玩家出生点 / 主基地上方放，否则 `unitRemove` 的 40×40 区域可能误删玩家建筑（即便填了 `spawnUnits`，也建议避开）。

## 六、与「城夺 / 古巴危机」生成器的关系

`gen_cuba.py` 已内置一段**天雷演示**（太平洋上空若干道，纯演出）：每个点一对 `天雷刷_X`（unitAdd, `turret*1(falling=true,offsetHeight=1400)`, team=-1）与 `天雷删_X`（unitRemove, `spawnUnits=turret`, team=-1, `delay=40`）。想关掉就删掉那段 `for (sx, sy) in [...]` 循环即可。
