# 铁锈战争 AI 地图创作 Skill

> 为 [铁锈战争](https://store.steampowered.com/app/647960/Rusted_Warfare/)（Rusted Warfare）制作 `.tmx` 地图的 AI Skill 套件。
> 作者：**三方同志** · 交流 QQ 群：**528400691**

本仓库包含两个版本，按需取用：

| 版本 | 目录 | 定位 |
|---|---|---|
| **2.0** | [`v2/`](./v2) | 基础版：地形生成 + 触发剧情两条线，附校验脚本 |
| **3.0** | [`v3/`](./v3) | 完整版：2.0 全部内容 + 现成地图生成器（KOTH / 城夺 / 古巴危机 / 4V4）+ 修边与通行性专项 + RW 1.15 单位表 |

---

## 快速开始

### 2.0

把 `v2/` 整个目录放进你的 AI 工具的 skills 目录即可，核心入口是 `v2/SKILL.md`。

```bash
# 地形渲染
python3 v2/scripts/gen_gids.py
python3 v2/scripts/verify_terrain.py grid_terrain.json gids.json

# 地图体检（C1~C10 硬性条件）
python3 v2/scripts/check_container.py 'X.tmx'
```

### 3.0

```bash
pip install pillow numpy

# KOTH 中岛争夺图（160×160 / 8 队）
python3 v3/gen_koth.py --out rw_koth.tmx --seed 7 --size 160 --teams 8

# 4V4 竞技遭遇战
python3 v3/gen_4v4.py
python3 v3/gen_4v4_rift.py

# 交付前自检（全绿才交付）
python3 v3/verify.py
```

成品可直接参考仓库内已验证的 `v3/rw_koth.tmx` 与 `v3/rw_cuba.tmx`。

> 3.0 的 `gen_cuba.py` 需要同目录的 `na.jpg`（北美洲参考图）作为陆地掩膜输入，本仓库未附带，请自备一张放进 `v3/` 即可。

---

## 目录结构

```
v2/
  SKILL.md                  # 主文档：两条主线 + 硬性条件总表 C1~C10
  references/               # 10 篇参考（地形/渲染/触发/踩坑）
  scripts/                  # 10 个可执行脚本

v3/
  SKILL.md                  # 主文档（含第三部分：RW 1.15 生成器）
  gen_koth.py               # KOTH 占点图生成器
  gen_cuba.py               # 古巴导弹危机 IF 线（图片抽形 + 事件链）
  gen_4v4.py                # 4V4 铁幕海峡
  gen_4v4_rift.py           # 4V4 干涸裂谷
  gen_combined.py           # autotile 角点投票引擎
  apply_ach_tiles.py        # 成就石碑自定义地块
  verify.py                 # 交付前自检
  references/               # 20 篇参考（含 RW 1.15 单位表、修边、通行性、职业图拆解）
  scripts/                  # 10 个校验/注入脚本
  rw_koth.tmx / rw_cuba.tmx # 已验证成品
  地面层整合.tsx/.png        # 完整地面图集（内嵌进单文件 tmx）
  misc.tsx/.png             # 水晶/树图集（含 res_pool）
```

---

## 核心要点

- **硬性条件 C1~C10**：三层 `Ground`/`Items`/`Units`（名精确·序固定·尺寸齐）、base64+gzip 数据、触发器只在 `Triggers` 且引用闭合。动手前先跑 `check_container.py`。
- **地形红线**：任一格四邻地形 ≤ 2 种（否则顶点采样出鞍点花屏）；特殊地形必须 ≥ 2×2 成片。
- **通行性红线**：跨水陆地桥必须是固定列窗口的宽矩形草地桥，核心 ≥ 20 列纯草地，交付前 BFS 验证连通。
- **触发链**：`activatedBy` 严格串行；检测器无 `activatedBy`、效果器写 `activatedBy=检测器名`。

---

## 许可

本 Skill 由「三方同志」制作分享。转载、二次分发请保留本署名与 QQ 群号 528400691。
