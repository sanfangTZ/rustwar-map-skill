# 踩坑清单（实战血泪）

## A. 终端 / 脚本执行
1. **禁止 `set -e`**：会让终端会话退出并卡死。
2. 写脚本推荐范式：
   `cat > /tmp/x.py <<'PYEOF' ... PYEOF` → `python3 /tmp/x.py > /tmp/o.txt 2>&1; echo EXIT=$?; cat /tmp/o.txt`
3. **一定要重定向输出**：漏重定向会出现 `/tmp/o.txt` 不存在、看不到结果。
4. heredoc 里的 `\b` 正则在终端回显常被吞（如 `TRIG_OBJS 0` 假阴性），不影响实际逻辑。
5. 终端回显中文文件名可能带空格，但实际执行不受影响，exitCode=0。
6. `find /sdcard` 大范围搜索务必加 `-maxdepth`，否则易超时。
7. `read_file` 不能 OCR PNG 图片。

## B. 文件 / 编码
8. **`ls` 字节数 ≠ Python `len()`**：中文 UTF-8 编码差异正常，以 Python 读取内容为准。
9. `/sdcard/...` 与 `/storage/emulated/0/...` 是同一路径的两个视图，复制一次即可。
10. 文件名里的中文，检索时以**实际文件名**为准（用户口语可能说反）。

## C. TMX 内容 / 校验
11. 原图常有 **id 重复**、**name 重复**、**旧悬空引用**，不要动它们，只做提示。
12. 用 `re.findall(r'<object[ >]', seg)` 统计对象数（含无 name 的），比只看 name 更准。
13. 插入锚点 = Triggers 段**最后一个 `</object>` 之后**、`</objectgroup>` 之前。
14. 校验三件套：① `ET.fromstring` 能否解析 ② 引用是否闭合 ③ 目标对象是否存在。
15. 错别字 / 繁体混入要专门 grep 检查（如 `清剥`、`結`）。
## D. 剧情设计
16. 不要用 `activate` 即时跳转串多条链（会同时点亮，节奏乱），**用 `activatedBy` 串行**。
17. 节奏用 `warmup` / `delay` 控时间；时间值记得带 `s`。
18. 结局分支用不同检测点/条件分流，确保两条链都有触发入口。

## E. 地形生成（血泪）
19. **采样分辨率陷阱（最坑）**：渲染是**顶点模型**——每格 tile 的四角由**周围 2×2 格多数投票**决定。所以**孤立单格**（尤其高石 14、岩浆 11）会被周围的草/石票数压平，渲染后**整片消失**。实测：铺 60 个孤立单格高石，gids 里一个相关 gid 都没有。**破解：成片 ≥ 2×2**，2×2 簇能让簇内 4 个顶点都拿到 ≥ 2/4 票。
20. **四邻 ≤ 2 种地形是根本约束**：任一格四邻出现 3 种地形，渲染时必中「缺失对角鞍点」→ 花屏。布局生成后要跑**迭代修复器**把违规降到 0。
21. **高石(14) 极娇气**：只兼容 草(0)/石(2)。与水(7)/岩浆(11)/雪(5)/高草(12) 全 BAD。放高石必须**先用 2 圈石(2) 做隔离带**，否则迭代修复器一破洞就贴到草上出错。详见 `terrain_compat.md`。
22. **三色灾难区**：`[0草,2石,14高石]`、`[0草,2石,11岩浆]` 这种组合在 3×3 邻域里合法率很低（实测 39/81、27/81），尽量别让三者直接相接。
23. **纯块统计要按 2×2 看**：判断「有没有被抹平」不能只看单格，要看 2×2 区块里目标地形是否仍 ≥ 2 票。
24. **gids 是二维数组**：每行是一串 gid（字符串或列表），别当一维数组处理，行列下标别搞反。
25. **渲染结果看「精确/模糊」**：`gen_gids.py` 输出的模糊计数应为 0 或极少；模糊多说明地形的四角组合命中了反查表缺项，需要检查布局或补组合。
26. **地形的 JSON 键是字符串 gid**：`ground_dict.json` 里 `tiles` 是 dict、键为字符串；`names` 是 list，**不能用 `.get()`**。
27. **出生点必须留 SAFE 区**：出生点 3×3（半径 ~3.4）内要**纯草**，不能有特殊地形，否则单位出生位置会卡。
28. **过渡件绝不能垂直平铺（实测血泪）**：把「上下过渡件」当平铺纹理**纵向重复堆叠**（如 `(197,197)×2 万`、`(89,89)×1.5 万` 这种同一 gid 垂直摞），会造成**垂直角值与相邻对严重不匹配**——实测一张图垂直角值不匹配 **67184 处**，而左右方向匹配率 82.3%（正常）。根因是**上下边缘本应交替使用成对的过渡 gid**（示例：`197` 下表边角 `(2,2)` 要接 `89` 的上表边角 `(2,2)`，两者**垂直交替**才连续），平铺成一片必然撕裂。**排查：统计 `(gid,gid)` 相邻对，看某 gid 是否与自己大量垂直相邻；修复方向是「补上下边的配对过渡件」而不是改左右边。**

---


---
> 署名：三方同志｜作者交流 QQ 群：528400691

## F. 随机刷兵（血泪，2026-10 实战）
29. **`unitAdd` 默认落矩形中心，不会自动随机铺开**：不知此点会以为「写了区域就会随机出」，实测每次都出在中心同一点。要随机必须显式加 `offsetRandomX/Y/XY`。
30. **负坐标会被 clamp**：检测区/出兵器若给了负 x（如 x=-200），引擎会归零/归位，导致原本分开的多个格子**重叠**、随机失效。坐标务必 0–3000 正整数。
31. **横向抽签只用 `offsetRandomX`，别用 `offsetRandomXY`**：`offsetRandomY` 会让落点 y 漂移，单位跑出 40px 细条检测区，抽签概率失真。细条检测区（h=40）尤其要只横向随机。
32. **同 `delay` 的多个 `unitAdd` 会共享随机种子 → 同步随机（最坑）**：两组抽签器若 `delay` 都是 `30s`，会在同一帧处理、拿到相同随机数 → 永远抽到同一格 → 「四个四个、四个相同」。**修法：不要靠多组独立抽签 + 错开 delay，改成「单组 + 每格刷一对组合」。**这是唯一稳解。
33. **想「每局必出 2 种、各 2 个」→ 把组合直接写进每格 `spawnUnits`**：如格1=`experimentalTank*2,experimentalHoverTank*2`，格2=`experimentalHoverTank*2,fireBee*2`，格3=`fireBee*2,experimentalTank*2`。这样无论抽到哪格，都是两种各两只，永远不出现 4 个相同。
34. **抽签器 x 要覆盖三格中心**：三格无缝 80–160 / 160–240 / 240–320（各宽 80）时，抽签器放 x=200、`offsetRandomX=120` → 随机 x∈[80,320] 恰覆盖三格，各 1/3 概率。
35. **heredoc 写中文脚本屡屡吞回显/乱码**：正确范式是 `cat > /tmp/x.py <<'PYEOF' ... PYEOF` 先落盘，再 `python3 /tmp/x.py > /tmp/o 2>&1`，最后**单独** `cat /tmp/o` 看结果。
36. **Python 脚本记得 `import re`**：漏了就 `NameError`，脚本直接失败还不报在回显里。

## G. spawnChance 真随机（顺序衰减抽签）
37. **`spawnChance` 是“按顺序逐个撑骰”，不是三选一**：同一 `spawnUnits` 里多个单位，引擎**按声明顺序**逐个尝试生成，每个各自独立撑骰。
38. **真出场率 ≠ `spawnChance`**：实际概率 = **自身 `spawnChance` × 前面所有单位失败率**。给值前先手算分布，别直接当权重用。
39. **`maxSpawnLimit` 会“卡上限跳过”**：该单位被撑中但会使累计数超过上限时，**跳过不生成**。所以靠后的单位可能“撑中了也出不来”。
40. **保底不出空**：最后一个单位给 `spawnChance=1.0, maxSpawnLimit=1` → 空局概率归零。
41. **单兵器内做真随机组合，优先用 `spawnChance`**：比“多组独立 `unitAdd`”更简单，且**避开了“时间戳随机种子同步”那个坑**。

## H. 重点坑：反例 vs 正解（XML 对照）
> 上面 A–G 是文字描述；这里把**最容易写错、一写错就出 bug 的 8 个坑**用真实 XML 对照出来，照着改就行。判断口诀：**❌ 反例 → ✅ 正解**。

### H1. 图层名 / 位置（官方硬性要求）
❌ 错：对象放在 `Ground`/`Units` 图层，或自己起个名 `Trigger`：
```xml
<objectgroup name="Trigger">   <!-- 大小写错 + 位置错，引擎直接忽略 -->
```
✅ 对：唯一合法图层名（**大小写敏感**），对象必须在里面：
```xml
<objectgroup name="Triggers" visible="false">
  <object id="1" name="map_info" x="0" y="0" width="20" height="20">
    <properties><property name="survivalWaves" value="+0:00 开始 - 3 tank"/></properties>
  </object>
</objectgroup>
```

### H2. name 含中文 / 连字符 / 空格
❌ 错：`name="第一波"`、`name="wave-1"`、`name="boss phase"` → 引擎无法引用/闪退。
✅ 对：只用**英文+数字+下划线**：
```xml
<object id="10" name="wave_1" type="unitAdd" x="300" y="300" width="20" height="20">
  <properties><property name="spawnUnits" value="tank*3"/><property name="team" value="1"/></properties>
</object>
```

### H3. 忘写 team（除 unitDetect 外）
❌ 错：`unitAdd` / `unitRemove` 不写 `team` → **闪退**（引擎拿不到归属）。
✅ 对：出兵器/移除器都显式写 `team`：
```xml
<object id="11" name="spawn_a" type="unitAdd" x="300" y="300" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2"/>
    <property name="team" value="1"/>   <!-- 1=游戏内 2 号位；0=1号位 -->
  </properties>
</object>
```
> 例外：`unitDetect` 的 `team` 可省略（省略=检测任意团队），但要检测特定团队时仍需写。

### H4. id 重复
❌ 错：两个对象都写 `id="5"` → 引用错乱、后面那个被忽略或悬空。
✅ 对：`id` 全图**唯一且为正整数**，新对象接着最大 id 往后编：
```xml
<object id="2004" .../>   <!-- 已有 -->
<object id="2005" .../>   <!-- 新增，不重 -->
```

### H5. 负坐标 / 错误尺寸导致抽签失效
❌ 错：抽签器负 x，或抽签器放三格正中却用 `offsetRandomXY`：
```xml
<object id="20" name="t" type="unitAdd" x="-200" y="-200" ...>
  <properties><property name="spawnUnits" value="mechMissile(offsetRandomXY=120)"/><property name="team" value="-2"/></properties>
</object>
```
✅ 对：坐标 0–3000 正整数，横向抽签只用 `offsetRandomX`，抽签器放三格正中 x=200：
```xml
<object id="20" name="t" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/>
    <property name="team" value="-2"/>
    <property name="delay" value="30s"/>
  </properties>
</object>
```

### H6. 多组独立 unitAdd 同 delay → 同步抽签（最坑）
❌ 错：开两组抽签器，`delay` 都写 `30s` → 同一帧、同随机种子 → 永远抽同一格（“四个四个”）
```xml
<object id="30" name="lot_a" type="unitAdd" ...><properties><property name="delay" value="30s"/>...</object>
<object id="31" name="lot_b" type="unitAdd" ...><properties><property name="delay" value="30s"/>...</object>  <!-- 同步！ -->
```
✅ 对：**只用单组抽签器**；要“每格必出多种”就把组合直接写进每格 `spawnUnits`（不用多组）：
```xml
<object id="2008" name="lot_g1_cell1_add" type="unitAdd" x="1300" y="1240" width="20" height="20">
  <properties>
    <property name="spawnUnits" value="tank*2,experimentalHoverTank*2"/>  <!-- 两种各2，永不出 4 同 -->
    <property name="team" value="1"/>
    <property name="activatedBy" value="lot_g1_cell1_det"/>
  </properties>
</object>
```

### H7. ticket（抽签信标）与 detector（探测器）team 未配对
❌ 错：信标 `team=-2`，探测器 `team=1` → **永远检测不到**，抽签失效。
✅ 对：信标与探测器**必须同 team**（本例 -2），只有真正刷给玩家的 `_add` 才用归属 team：
```xml
<object id="2004" name="lot_g1_ticket" type="unitAdd" x="200" y="2620" width="20" height="20">
  <properties><property name="spawnUnits" value="mechMissile(offsetRandomX=120)"/><property name="team" value="-2"/></properties>
</object>
<object id="2005" name="lot_g1_cell1_det" type="unitDetect" x="120" y="2620" width="40" height="40">
  <properties><property name="unitType" value="mechMissile"/><property name="team" value="-2"/><property name="minUnits" value="1"/></properties>
</object>
```

### H8. spawnChance 把裸概率当权重 / 忘了保底
❌ 错：以为 `spawnChance` 是均匀权重，且末尾不留保底 → 有概率整波不出兵：
```xml
<property name="spawnUnits" value="tank*1(spawnChance=0.5),fireBee*1(spawnChance=0.5)"/>  <!-- 25% 空出 -->
```
✅ 对：真出场率 = 自身 × 前面全失败；最后一个单位给 `spawnChance=1.0, maxSpawnLimit=1` 保底：
```xml
<property name="spawnUnits" value="tank*1(spawnChance=0.5),fireBee*1(spawnChance=0.4,maxSpawnLimit=1),mechlightning*1(spawnChance=1.0,maxSpawnLimit=1)"/>
```
> 注：上例坦克 50% / 火蜂 (0.5×0.4)=20% / 特斯拉 (0.5×0.6×1.0)=30% / 空 0%。

---
