# TMX 地图文件压缩（瘦身，非尺寸缩放）

> 融合自用户提供的 `压缩地图.html`（作者 wty-hub，纯前端本地处理，文件不上传服务器）。
> 经核验：该工具逻辑正确，本文档将其方法论抽成规范。**注意：这是“压文件体积”，不是“等比缩小地图尺寸”**——地图的格数、玩法、触发器逻辑完全不变，只是把 .tmx 文本里冗余的节点和名字“减肥”。

---

## 〇、什么时候用

- 地图文件太大（几百 KB ~ 几 MB），想减小体积、加快加载、方便分享。
- **不适合**：想改变地图尺寸/地形布局（那是第一部分地形生成线的缩放，不是本篇）。
- 压缩后游戏内完全正常，只是触发器名字变成 `a/b/c…` 这种短串，可读性下降——**交付给玩家没问题，自己后续手改触发时记得先解压或对照**。

---

## 一、可安全删除的节点 / 属性

| 删除项 | 路径 / 写法 | 为什么能删 |
|---|---|---|
| 图片引用 | `tileset > image` 节点 | 地图在游戏里不依赖 tmx 内嵌的图片引用；图集由游戏按 tsx 加载 |
| tileset 名 | `tileset` 上的 `name` 属性 | 纯标识，运行期无用 |
| 单位对象名 | `UnitObjects` 图层里所有 `object` 的 `name` 属性 | 单位对象靠 `type`/坐标定位，name 不参加任何引用 |
| 未引用的触发名/ID | 触发器 `object` 的 `name`（除 `map_info`）和 `id` 属性值，若从没被别人引用 | 没人指它，删了不影响链条 |
| 空白文本节点 | 序列化时移除 | 纯缩进/换行，无语义 |
| XML 声明 | `<?xml …?>` | RW 读取 tmx 不需要声明头 |

> ⚠️ **唯一必须保留名字的对象**：`map_info` 的 `name` 不能动、不能删、不能重命名——它一旦丢失，整个触发系统不启动（见 `trigger_objects_v26.md` A 类）。

---

## 二、触发器引用关系（最关键的一步）

触发器之间靠 5 个**引用属性**互指名字。这些名字**绝不能删**，只能“缩短”：

```js
const REFERENCE_PROPERTIES = [
  "activatedBy",      // 任一来源激活即触发
  "deactivatedBy",    // 指定来源触发时禁止触发
  "target",           // move 的目的地（= point 的 name）
  "alsoActivate",     // 同时激活另一个
  "whenActivatedIds", // 类 activatedBy（按 id 引用）
];
```

**最短串重命名算法**（原文 `genMinimalStrings` + `product`）：

1. 收集候选引用名：遍历 `Triggers` 里所有 object 的 `name`（非 `map_info`）和 `<property name="id">` 的值。
2. 统计每个候选名在 `REFERENCE_PROPERTIES` 这 5 个属性里**被引用的次数**。
3. 只保留**被引用过（次数≠0）**的名字，按引用频次从高到低排序。
4. 用 36 字符集 `a-z0-9` 生成最短唯一串：`a,b,…,z,0,1,…,9,aa,ab,…`（单字符 36 个用完后展开到双字符），依次替换这些名字。
5. 同步替换三类位置：
   - 触发对象自身的 `name` 属性；
   - 其 `<property name="id">` 的值；
   - 所有引用属性（`activatedBy` 等）里出现的对应值。
6. 没被引用的 `name` 直接删除，`id` 属性直接删除（减少体积）。

> 频次排序的意义：被引用最多的触发器拿到最短名字（如 `a`），进一步压体积。

---

## 三、序列化要点

- 用 `XMLSerializer` 序列化前，递归删除所有纯空白 `TEXT_NODE`（缩进换行）。
- 去掉开头的 `<?xml …?>` 声明。
- 结果即为压缩后的 tmx 文本，另存为 `原名_compressed.tmx`。

---

## 四、核心源码（来自 `压缩地图.html`，已核验）

```js
function compressMap(xmlText) {
  const doc = new DOMParser().parseFromString(xmlText, "application/xml");
  if (doc.querySelector("parsererror"))
    throw new Error("XML 解析失败");
  if (doc.documentElement.tagName !== "map")
    throw new Error("不是有效的 TMX 地图文件（根节点应为 map）");

  // 1) 删 tileset 图片 + tileset name
  doc.querySelectorAll("tileset > image").forEach(n => n.remove());
  doc.querySelectorAll("tileset").forEach(s => s.removeAttribute("name"));

  // 2) 删 UnitObjects 里所有 object 的 name
  const uo = doc.querySelector('objectgroup[name="UnitObjects"]');
  if (uo) uo.querySelectorAll("object").forEach(o => o.removeAttribute("name"));

  // 3) 触发器：收集引用名 → 频次排序 → 最短串替换
  const REF = new Set(["activatedBy","deactivatedBy","target","alsoActivate","whenActivatedIds"]);
  const trig = doc.querySelector('objectgroup[name="Triggers"]');
  if (trig) {
    const refs = new Map();
    trig.querySelectorAll("object").forEach(o => {
      const n = o.getAttribute("name");
      if (n && n !== "map_info") refs.set(n, 0);
      o.querySelectorAll('properties > property[name="id"]').forEach(id =>
        refs.set(id.getAttribute("value"), 0));
    });
    trig.querySelectorAll("object").forEach(o =>
      o.querySelectorAll("properties > property").forEach(p => {
        if (REF.has(p.getAttribute("name"))) {
          const v = p.getAttribute("value");
          if (v !== null) refs.set(v, (refs.get(v) || 0) + 1);
        }
      }));
    const used = [...refs.entries()].filter(([,c]) => c !== 0)
                  .sort((a,b) => b[1]-a[1]);
    const mini = genMinimalStrings(used.length);
    const map = new Map(); used.forEach(([k], i) => map.set(k, mini[i]));

    trig.querySelectorAll("object").forEach(o => {
      const n = o.getAttribute("name");
      if (n && n !== "map_info") {
        if (map.has(n)) o.setAttribute("name", map.get(n));
        else o.removeAttribute("name");
      }
      o.querySelectorAll('properties > property[name="id"]').forEach(id => {
        const v = id.getAttribute("value");
        if (map.has(v)) id.setAttribute("value", map.get(v));
        else id.remove();
      });
      o.querySelectorAll("properties > property").forEach(p => {
        if (REF.has(p.getAttribute("name"))) {
          const v = p.getAttribute("value");
          if (v !== null && map.has(v)) p.setAttribute("value", map.get(v));
        }
      });
    });
  }
  return serializeXml(doc); // 去声明 + 去空白文本节点
}
```

> `genMinimalStrings(n)`：用字符集 `abcdefghijklmnopqrstuvwxyz0123456789`，先生成全部 1 位串（36 个），不够再 2 位、3 位……保证唯一且最短。`serializeXml` 递归删除空白 `TEXT_NODE` 并去掉 `<?xml?>` 头。

---

## 五、使用方式

- **随 Skill 附带的现成工具**：`压缩地图.html`（与本 Skill 同目录，纯前端、本地运行、文件不联网）。直接双击用浏览器打开 → 拖入 / 选择 `.tmx` → 点「压缩地图」→ 点「下载压缩后的 .tmx」。它会自动显示原大小 / 压缩后 / 压缩率 / 节省。
- 也可按上面算法自己写脚本（Python/JS 均可），逻辑一致。

## 六、自检清单

- [ ] `map_info` 的 `name` 仍在、未被替换/删除
- [ ] 压缩后所有 `activatedBy`/`deactivatedBy`/`target`/`alsoActivate`/`whenActivatedIds` 的值都能在 Triggers 里找到对应（无悬空引用）
- [ ] 游戏内能正常开局、触发链不断
- [ ] 体积确实下降（工具会显示原大小 / 压缩后 / 压缩率 / 节省）

> 署名：wty-hub（原工具）｜本 Skill 融合整理。
