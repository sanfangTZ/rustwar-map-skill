# 凭空画国家：公益地理 API 实测指南（V4.2）

> V4.1 已实测闭环：`gen_country.py` 日本/德国双 demo 全指标通过。
> 数据只是"打底素材"（矢量边界），不是成品图，符合零成品图政策。

## 一、公益 API 选型（实测结论）

| 数据源 | 结论 |
|---|---|
| **geoBoundaries gbOpen** ✅ 采用 | `https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM}/`，CC BY 4.0，无需 key。返回 JSON 含 `gjDownloadURL`（GeoJSON 矢量）与 `simplifiedGeometryGeoJSON`（简化版，优先用，小一个量级）。覆盖全球 ADM0/ADM1/ADM2 |
| restcountries v3.1 ❌ | 已废弃（返回 deprecation），且只有国旗没有地理图 |
| Natural Earth | CC0 备选，但行政边界精度低（大 国 OK 小国糊） |
| Wikimedia blank maps | SVG 空白图，需二次矢量化，麻烦 |
| OSM Overpass | ODbL 可用但限流严、拉全国慢，不建议 |

## 二、三个实测坑（必读）

1. **GitHub LFS 指针**：geoBoundaries 矢量托管在 GitHub LFS。`raw.githubusercontent.com`
   直链只会拿到 131 字节指针文件——必须改写为
   `https://media.githubusercontent.com/media/{owner}/{repo}/{path}`（脚本已自动处理）。
2. **网络抖动**：API 偶发 RemoteDisconnected，脚本已内置 3 次重试；
   拉下来的矢量缓存在 `data/geo/{ISO3}_{ADM}.geojson`，二次生成走缓存。
3. **首 ISO 查询**：用 ISO3 编码（JPN/DEU/USA/CHN…），国名不行。

## 三、gen_country.py 流程（6 步）

```
python3 gen_country.py JPN 日本 --cap 35.68,139.69
python3 gen_country.py DEU 德国 --cap 52.5,13.4
```

1. 拉 ADM1（一级行政区）GeoJSON，47 都道府县 / 16 州。
2. `matplotlib.path` 栅格化成 200×200 区划掩膜（等积近似：经度 × cos(中纬)）。
3. 气候地形：**每行政区一个"地貌基因"**（草主/土主 + 林地比 + 水田比）拼花出
   可辨认的区划；海岸 1 圈沙滩；内陆隆起成山（STONE 外圈 + HIGHSTONE 内核）。
4. **内陆隆起按该国最大纵深归一化**（`dmax*0.8`）——大国（德国）不会整片内陆
   变高山，小国（日本）也能拱出脊线。★固定步距是踩过的坑：德国曾 15.6% 高石。
5. 区界只做 **p=0.3 的 DIRT 虚线省道点**。★小区划国家（47 区挤 1600 格）若逐格
   刻界会把全国刻成泥巴——区划主要靠地貌拼花表现，虚线只做点缀。
6. 基地：**同一座主岛（最大 4 连通块）**上，首都（`--cap 纬度,经度`）落队 0，
   BFS 直径端点落队 1（天然陆地互达）。★不要选"相距最远的两个区府"——
   那会选到北海道+九州两个孤岛，然后公路斜穿大海。区府放水晶，Q1/Q2/Q3
   三门槛自动执行，产出 .tmx + 标注预览 PNG。

## 四、真实高程 DEM + 真实水系（V4.2 重磅升级）

### 4.1 数据源：AWS Terrain Tiles（Mapzen/Tilezen terrarium，CC-BY 4.0，免 key）
```
https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
```
- **terrarium 编码**：`elev = R*256 + G + B/256 - 32768`（米，可为负=海底）。
- **Web Mercator（slippy map）瓦片坐标**：`x=(lon+180)/360*2^z`，
  `y=(1-ln(tan(lat)+1/cos(lat))/pi)/2*2^z`。⚠️ 别拿"等经纬"瞎算坐标——
  404 八成是算到南极去了。
- **zoom 自适应**：瓦片数 >160 就降一级。z=7≈1.2km/px，日本~40 块、德国~12 块，
  200×200 图有 4~9 倍超采样，绰绰有余。
- bbox 用**经纬度 2/98 百分位**裁剪（防离岛把 bbox 撑爆，如日本的小笠原）。
- DEM 按国家缓存到 `data/geo/dem_{z}_{lon0}_{lat0}.npz`，二次运行零网络。

### 4.2 真实山脉（分位数自适应，弃 fbm 假隆起）
- `t_stone = p82(elev)` → STONE（山地 ≈ 陆地 18%）；`t_high = p95(elev)` → HIGHSTONE（≈5%）。
- **百分位而非绝对海拔**：平原国（荷兰 p95≈100m）几乎无山、山国（瑞士）满山，全自动适配。
- 坡度（8 邻最大落差/距离，归一化到 (p95-p50)）辅助成崖：`slope_n>0.20→STONE、>0.45→HIGHSTONE`。
- HIGHSTONE 只留极端峰/极陡崖——**HIGHSTONE 不可通行，大面积山墙会把国家拦腰截断**。

### 4.3 真实河流（D8 汇流分析）
- 每格流向 8 邻中最陡下坡；**累计必须降序处理**（上游先把自己累加传给下游），
  升序会把中间格累计值算小一个量级（德国曾因此 0 河流）。
- 阈值 `thr = max(6, 0.08*max_acc)`（主干流级别），总量保护：>陆地 8% 就抬阈值。
- 落 **SHOAL 浅水**而非 WATER——SHOAL 不在 IMPASS，可通行，天然 choke point，
  河流再密也不破坏连通，无需修桥。
- 河流必须在 `edge_auto_fix` **之后**落笔：clean_all 会把 1 格宽河道当尖刺抹掉。

### 4.4 海岸线回注（clean 的副作用修复）
- clean_all 会把**单像素宽的真陆桥/海角**（如日本濑户内海的细链）当尖刺溶成 OCEAN，
  若基地恰好落在上面就直接变孤岛。
- 修法：修边后按 region 掩膜回填——`region 陆地 且 grid∈(OCEAN,SEA,WATER) → SAND`。
  真实海岸线由矢量掩膜定义，修边只清 inland，不蚀海岸。

### 4.5 近岸浅水带与水域碎屑清理（V4.2 细节美观）
- 海域一水到底全是 OCEAN 会与沙滩硬切。用**多源 BFS 距离场**（8 邻切比雪夫，
  从全部 region 陆地格出发）生成等宽 2 格浅水带：`dist<=2 的海格 → WATER`，
  环带与海岸平行=等深线效果，带宽均匀。
- 带子两类 1px 碎屑及清理（只动水、不碰陆地）：
  · **飘出蓝点/细须**：4 连通 WATER 分量 <4 格 → 沉回 OCEAN（主带是长连通环，不受影响）；
  · **带内单格孔洞**：8 邻 ≥6 格 WATER 围着的 OCEAN 格 → 补成 WATER。
- **致命坑（实测）**：孔洞规则若写成"8 邻 ≥6 格**水类**（WATER∪OCEAN）"——深海格
  8 邻全是 OCEAN 也满足，**整片大洋被补成浅水**（日本图 94% 变 WATER、深浅全丢）。
  **邻居统计必须精确到单一目标类别**。发现线索：自检报告"地形分布 水 94%/洋 2%"；
  实锤方法：预览像素取样对比图集 tile 色（WATER≈(18,83,178)、OCEAN≈(0,22,70)）。
- 反推地形类别的诊断法：Ground 层 GID 减 firstgid 得 tid → 查 TSX terrain
  角属性取众数（TSX 角索引与生成器常量同序：0草/1土/2石/3沙/4泥/7水/8海/9洋/
  12高草/14高石/23浅滩）。可量化"水类交界邻接边数"等指标。
- 装饰去石：`make_decor` 新增 `stone_decor=False`（国家图关掉石滩/尖柱簇），
  `sand_tiles`/`mud_tiles` 参数化只传草簇/花——山地保持净空，装饰只剩花草树。

### 4.6 连通性判定必须与 verify 完全一致
- `verify_connectivity` 用 `bfs_dist`（4 邻接 + IMPASS={WATER,SEA,OCEAN,HIGHSTONE}）。
- `ensure_connected` 曾用 8 邻接 + 只避 HIGHSTONE：对角缝和水路都被它当"连通"，
  与 verify 打架。已统一为 4 邻接 + G.IMPASS 全套。
- 真实山墙隔断基地时：A*（可通行=1、HIGHSTONE=50）找最低代价路，把 HIGHSTONE
  凿成 3 格宽 STONE 走廊（中心格 4 邻同类≥3，不会被 clean 抹掉）。

## 六、实测记录（V4.2，真实 DEM + 河流）

| demo | 结果 |
|---|---|
| DEU 德国 | 16 州、北部绿平原+中部高原(哈茨/图林根)+南部阿尔卑斯山麓全部对位、莱茵/易北/多瑙/奥得河网 690 格、终检修边 99.89%、深浅水层次（洋 54.8%/水 4.8%）、连通 True、触发器 0 问题、装饰全白名单 |
| JPN 日本 | 47 区、真实山脉脊柱(最高 2550m)+71 格河流、终检修边 99.98%、深浅水层次（洋 93.2%/水 2.8%）、连通 True、触发器 0 问题、装饰全白名单 |

## 七、可调参数

| 参数 | 位置 | 效果 |
|---|---|---|
| `--cap` | 命令行 | 首都经纬度，队 0 落位 |
| `--seed` | 命令行 | 地貌基因随机种子 |
| `DEM_Z=7` | gen_country.py | DEM 缩放级（自适应降级保底） |
| `p82 / p95` | climate_terrain | 山地/极端峰占比门槛（分位数） |
| `thr = max(6, 0.08*max_acc)` | compute_rivers | 河流多寡 |
| `p=0.3` | region_borders | 省道虚线密度 |
| 乡野点缀 5%/3% | generate | 陆地装饰密度 |
