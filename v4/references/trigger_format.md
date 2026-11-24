# 铁锈战争 Triggers 触发对象写法模板

所有 object 必须在 `<objectgroup name="Triggers">` 内。每个 object 通用属性：
`id` / `name` / `type` / `x` / `y` / `width` / `height`，并带 `<properties>`。

属性名用**驼峰**（spawnUnits/activatedBy/warmUp/unitType/minUnits/maxUnits），例外：
`globalMessage_textColor` / `textOffsetX` / `textOffsetY`。
时间值**必须带单位**（`2s`、`0.15s`），布尔**小写**，team 用 `-2/-1/0/1`。

---

## 1. 基础结构
```xml
<object id="9101" name="修复完成" type="unitDetect" x="100" y="100" width="20" height="20">
  <properties>
    <property name="unitType" value="heavyTank"/>
    <property name="activatedBy" value="移动到修复点"/>
  </properties>
</object>
```

## 2. 单位进入检测（unitDetect）
条件：某单位进入某个矩形区域。常配合 `activatedBy` 串接前一条。
```xml
<object id="9102" name="修复对话2" type="unitDetect" x=".." y=".." width="20" height="20">
  <properties>
    <property name="unitType" value="plasmaTank"/>
    <property name="warmup" value="2s"/>
    <property name="activatedBy" value="修复完成"/>
  </properties>
</object>
```

## 3. 内心独白 / 旁白（basic）
立即触发的纯脚本对象。
```xml
<object id="9104" name="结晶疑云" type="basic" x="0" y="0" width="20" height="20">
  <properties>
    <property name="warmup" value="2s"/>
    <property name="activatedBy" value="jzz修复对话"/>
    <property name="action" value="..."/>
  </properties>
</object>
```

## 4. 全屏文本 / 对话（mapText）
写法用 `text` + `textSize` + `textColor`（不要用错字段名）。
```xml
<object id="9111" name="抉择" type="mapText" x="0" y="0" width="20" height="20">
  <properties>
    <property name="text" value="要留下守城，还是出城看看？"/>
    <property name="textSize" value="30"/>
    <property name="textColor" value="yellow"/>
    <property name="warmup" value="2s"/>
    <property name="activatedBy" value="管理员坦白"/>
  </properties>
</object>
```

## 5. 生成单位（unitAdd）
```xml
<object id="9105" name="虫群来袭" type="unitAdd" x=".." y=".." width="20" height="20">
  <properties>
    <property name="spawnUnits" value="bugWasp"/>
    <property name="minUnits" value="3"/>
    <property name="maxUnits" value="3"/>
    <property name="team" value="-2"/>
    <property name="warmup" value="1s"/>
    <property name="activatedBy" value="结晶疑云"/>
  </properties>
</object>
```

## 6. 移除单位（unitRemove）
写法用 `warmup` + `activatedBy`。
```xml
<object id="9108" name="清剿" type="unitRemove" x="0" y="0" width="20" height="20">
  <properties>
    <property name="unitType" value="bugWasp"/>
    <property name="maxUnits" value="999"/>
    <property name="warmup" value="8s"/>
    <property name="activatedBy" value="重坦护驾"/>
  </properties>
</object>
```

## 7. 分支跳转
- `activate`：即时激活目标（**慎用**，会同时点亮多条链，节奏乱）
- `activatedBy`：被目标激活才触发（**推荐**，用于严格串行）
- `alsoActivate`：同时激活另一个
- `delay`：延迟执行（如 `8s`）

---

## 8. 严格串行链的最小示例
```
修复完成 --activatedBy--> 修复对话2 --activatedBy--> jzz修复对话
  --activatedBy--> 结晶疑云 --activatedBy--> 虫群来袭 --activate--> 重坦护驾
  --activatedBy--> 清剿 --activatedBy--> 真相揭露 --activatedBy--> 管理员坦白
  --activatedBy--> 抉择 --activatedBy--> 结局A / 结局B
```

## 9. 引用闭合检查
所有 `activatedBy` / `activate` / `alsoActivate` / `target` 的 value，
必须能在 Triggers 段里找到同名 `name`，否则链条断裂。

---

---
> 署名：三方同志｜作者交流 QQ 群：528400691
