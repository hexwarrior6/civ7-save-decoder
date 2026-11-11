# Phase 6 — 地图图元区与资源分布（地形/资源/道路/单位存在位）

> 2026-11-12。工具：`tools/terrain.py`（`python3 -I tools/terrain.py <body.bin> <out.json>`，
> import 复用 `propertybag.py` 的 `crc32_name`）。验证档：E0/E1/E2/E5.2（远古同局）+ MODERN
> （AutoSave_02_0027，**另一局**）。结论全部经 CRC 反查 + 跨档差分 + 城市锚点三重验证。

## 1. 定位：地图数据在 Plots 块（不是 phase1 预估的 0x4d6dd0）

Phase1 §5 标注的两个大区实为**三**个不同区域（重定界）：

| 区域 | E0 偏移 | 大小 | 内容 | 状态 |
|---|---|---|---|---|
| **Plots 块**（hash `0x4b8d928f`，字段名 `Plots`） | 0x2f59e2 块头，数组 0x2f5a4d | ~249KB | **每格一条记录**，本文主题 | ✅ 已解 |
| FeatureLayoutCache（hash `0xa6d4bb6b`/`0x5a9d3461` 嵌套） | 0x3364e9 | 1.16MB | 含多个 `[5][hash][0][3404][74][3404]` 子数组 + 148B 周期稀疏段 | ⚠️ 未解（E1 有 ~20B 变化，疑单位移动缓存） |
| 0x4d6dd0 区（phase1 的"地图图元区"） | 0x4d6dd0 | 375KB | `[hash][1][1][0xa00048]` 头 + u16 对流，尾部 20B 记录 `[-1][-1][-2][0]` | ⚠️ 未解（E0/E1 完全一致 = 静态） |

Plots 块语法 = phase1 已解的块语法：`[hash 0x4b8d928f][1][-1][1][1][2]` + schema
`[(Properties,0x402), (Plots,0x402)]`，Plots 为容器形 0x402（`[len=1]["\0"][FXSBLKED]` 无终止）。
容器负载头（20B）+ 填充（12B）+ 前奏（12B）：

```
01 00 00 00 | 4a 00 00 00 | 2e 00 00 00 | 06 00 00 00 | 4c 0d 00 00   ← [1][W=74][H=46][6][W*H=3404]
00 00 01 00  00 00 01 00  00 00 01 00                              ← 3 x u32 0x00010000（未解）
ff ff ff ff  00 00 00 00  06 00 00 00                              ← 与记录尾同构（未解）
```

四档实测 W/H：E0/E1/E2/E5.2 = 74×46；**MODERN 也是 74×46**（原以为大图回归，实际 MODERN 是
另一局的小图：大陆名 KERNORLAND/AMASIA/PANNOTIA/RODINIA ≠ E0 的 SIBERIA/AVALONIA/AUSTRALIA/
ANTARCTICA，地形分布不同）。因此"W 可变"只在头部解析层面验证（工具从头部读 W，不硬编码 74），
"不同尺寸地图"的 stride 普适性**未测**——记录自定界，理论上与 W/H 无关。

## 2. plot 记录语法（核心成果）

数组 = W*H 条记录。**记录以地形类型 CRC 哈希开头、自定界**（下一条 = 200B 内下一个地形哈希）：
常规 73B；自然奇观格 125B（多 52B 奇观数据）；**最后一条只有 49B（无 24B 尾）**。
73 = 49B 主体 + 24B 尾。数组后紧跟 FXSBLKED 终止符 + CityAttributes 块。

### 2.1 主体 49B 字段表（偏移经 3404 格全量列统计 + CRC 反查 + 差分验证）

| 偏移 | 类型 | 字段 | 证据 |
|---|---|---|---|
| +0 | u32 | **地形类型** CRC（TERRAIN_OCEAN/COAST/FLAT/HILL/MOUNTAIN/NAVIGABLE_RIVER） | 3404/3404 反查命中；`dd 09 c9 47`=TERRAIN_OCEAN 即 phase1 的"记录起始标记" |
| +4 | u32 | **生物群系** CRC（BIOME_MARINE/GRASSLAND/PLAINS/DESERT/TROPICAL/TUNDRA） | 3404/3404 命中 |
| +8 | u32 | **大陆** CRC（CONTINENT_*）或 -1=水域无大陆 | 1275 命中 = 陆地 1229 + 可航河 46 ✓ |
| +12 | u16 | **高度场**：0=海洋连体水、200=湖、陆地 20–290（平地多为 100）、山 180（131/134 格） | 46 个 u12=200 的 COAST 与"无大洋邻居的湖岸"46/46 完全重合；地图渲染呈平滑梯度 |
| +14 | u16 | 未解（静态；0 占多数，其余多为 100 的倍数至 1100+，平地专属倾向） | E0=E2=E5.2 逐格相同 |
| +16 | u8 | 未解（0 或 2；水 0，COAST 26%为2） | 静态 |
| +17 | u8 | 未解（255=海、0/1/2=陆；海恒 255） | 静态 |
| +18 | u8 | 未解（≤2^6 位内位掩码，值 0/1/2/4/8/16/32/48…；与邻居水/山/河位掩码均无相关） | 静态；暴力试过 2 种六邻奇偶、山/水/可航河 = 不匹配 |
| +19 | u32 | **特征** CRC（FEATURE_ICE/FOREST/REEF/…）或 -1 | 924 命中（含 30 种） |
| +23 | u16 | 未解（奇观格 02/03，其它 0） | 静态 |
| +25 | u32 | **资源** CRC（RESOURCE_*）或 -1 | 278 命中，与 +29 非零数 278 一致 |
| +29 | u8 | 0/1（资源格恒 1，疑"有资源"或数量级） | 与资源哈希 100% 对齐 |
| +31 | u32 | **道路** CRC（ROUTE_ROAD）或 -1 | E0 16 → E5.2 20 → MODERN 285，随修路增长 ✓ |
| +35..40 | 6B | 未解（ff×7 连段的后半，疑与 +31 同为一个 u64/结构） | 静态 |
| +41 | u8 | **单位存在位**（0/1） | E0 68 个 1 = units.py 69 单位中 68 个落点完全一致（唯一例外 UNIT_MIGRANT 两处均不置位）；E1 差分恰在开拓者新旧格 489→487 |
| +42 | u8 | 未解：255=水/山、0=丘陵、1/2=平地（静态、盐椒状，与 biome/高度无关） | 静态 |
| +43 | u16 | **地块上城区/城市实例 id**（城市中心非 0：E0 7 城 = 125/36/96/184/43/50/103；MODERN 51 城全部非 0；全域 1174 格非 0 = 城区+奇观等） | 动态（随建造变化） |
| +45 | u16 | 与 +43 成对出现（城市格非 0：1,8,15,22,29…步进 7） | 动态 |
| +47 | u8 | bit3=**冰雪**（海冰 268 格=FEATURE_ICE 全量、雪山恒 1），bit4–6=未解 3bit 变体 | 静态 |
| +48 | u8 | 恒 0（对齐） | |

### 2.2 尾 24B（+49..72，末条记录无）

```
[8 × i16][u32 g][u32 6]
```
- 8 个 i16 = 4 个 (start,end) 区间对；前 3 对值域与 Areas/Hemispheres/Landmasses 容器头
  的容量 `[16][120][117] / [16][96][93] / [16][32][31]` 吻合（对0≤115、对1≤90、对2≤25），
  **推测 = 该格所属 area/hemisphere/landmass 的 [start,end) 区间（每格通常恰含 1 个成员）**；
  对 3 常为 (-1,-1)（2309 格）。归属"本格 vs 下一格"已用海岸线差分（陆地格尾=陆地簇、
  相邻水格尾=水簇）判定为**本格**。
- g：0 占 95%，少量 1–33（未解）；h：恒 6（疑=六边形边数），少数 16–37（未解）。
- 奇观格（125B）在 +49..+100 插入 52B：含常量 `0x1d2f95b3`、`0x4344acef`（全部奇观格相同，
  未反查到名）+ 少量计数，结构未解。

## 3. E0/E1 差分（分离静态 vs 动态）——决定性证据

9,573,774 B 逐字节 diff = **46 个字节**，分 6 组：
plot 数组仅 2B（plot489 的 +41 由 1→0、plot487 的 +41 由 0→1，= 开拓者离开/到达）；
FeatureLayoutCache 20B（两组 ×3 簇、每簇 4 个连续 u16、簇距 146–150B，值 ±1 变化，未解，
疑为移动/寻路缓存）；其余 24B 在单位块（位置/移动力，phase1 已解）。

**结论：plot 数组 = 静态地形层 + 4 个动态字段（+41 单位位 / +43/+45 城区 id / 道路 / u39 小计数）。**
E0 vs E5.2 逐格对比：仅 unit/u39/u43/u45/road 变化（109/13/16/16/4 格），其余全部逐格相同；
E0 vs E2 全部静态字段逐格相同。**探索迷雾不在 plot 数组。**

## 4. CRC 反查结果（E0）

- 地形 6 种：OCEAN 1485 / FLAT 863 / COAST 690 / HILL 184 / MOUNTAIN 134 / NAVIGABLE_RIVER 48
  （LandPlots=1229 = FLAT+HILL+MOUNTAIN+NAV_RIVER ✓ 与 root 块 LandPlots 字段吻合）
- 生物群系 6 种：MARINE 2175 / TROPICAL 312 / PLAINS 263 / GRASSLAND 243 / TUNDRA 226 / DESERT 185
- 大陆 4 + 水域：SIBERIA 408 / AUSTRALIA 402 / AVALONIA 301 / ANTARCTICA 164（名池来自
  游戏本体 XML，存档内无明文）
- 特征 30 种 924 格：ICE 268 / RAINFOREST 99 / TAIGA 84 / REEF 79 / FOREST 71 / SAVANNA_WOODLAND 56
  / ATOLL 49 / SAGEBRUSH_STEPPE 30 / COLD_REEF 25 / OASIS 21 / MANGROVE 20 / VOLCANO 17 /
  TROPICAL_FLOODPLAIN_MINOR 17 / TROPICAL_FLOODPLAIN_NAVIGABLE 16 / WATERING_HOLE 15 / …（含 3 自然奇观名）
- 资源 26 种 278 格：CRABS 33 / FISH 33 / COWRIE 33 / SILVER 13 / FLAX 13 / IVORY 12 / GOLD 12 /
  SALT 9 / HARDWOOD 9 / CAMELS 9 / WILD_GAME 8 / JADE 8 / WOOL 8 / SILK 8 / GYPSUM 7 / IRON 7 /
  KAOLIN 7 / COTTON 7 / LIMESTONE 7 / RUBIES 6 / WINE 6 / HORSES 6 / MANGOS 6 / LLAMAS 6 / TIN 3 / PEARLS 2
  （MODERN 23 种 286 格：OIL 25 / COAL 24 / NITER 23 / FURS 23 / …，时代资源替换可见）
- 自然奇观 11 格 3 个：TORRES_DEL_PAINE（3 山格）/ THERA（4 海岸格）/ BARRIER_REEF（4 海岸格）；
  MODERN 13 格 4 个（KILIMANJARO/GRAND_CANYON/ZHANGJIAJIE/THERA）→ **125B 记录 = 自然奇观格** ✓

## 5. 城市锚点自洽

- 圣彼得堡（RUSSIA1）plot489=(45,6)：FLAT / TUNDRA / SIBERIA，u43=125 ≠ 0（城心 id）✓ 陆地
- 图拉（RUSSIA7，E5.2）plot708=(42,9)：FLAT / TUNDRA / SIBERIA ✓ 陆地
- E0 7 城、E5.2 8 城、MODERN 51 城 **全部落在陆地格**（51/51），无一座落在水/山上
- MODERN 城市格 u43 全非 0 ✓ 与 +43=城心 id 一致

## 6. 探索迷雾 —— 未解（如实标注）

- plot 数组无迷雾位（E0/E1 差分证明：同回合移动不产生迷雾变化是预期，但数组内也无
  任何 255/位图字段随探索变化——E0/E2/E5.2 静态字段逐格相同，而探索范围在增长）。
- 已定位：每玩家块 hash_b6be9ade 只存 `PlotsRevealed` **计数**（Int）。E0 31 个值
  （164/175/205/209/214/185/138/148…），E5.2 增长（181/187/208/227…），MODERN 19 块
  （785/586/545…，死者块消失）。**计数→位图本体未找到**。
- 已排除：0x700000–0x880000 每玩家区内的 524B/509B/999B 数组 = 对象图节点流（非位图）。
- 下一步：① 定界玩家 Properties 0x402 容器（phase1 U3b 遗留）找 `Visibility` 组件；
  ② 找一对"单位揭示新地块"的存档差分（E0/E1 无效，因移动在已探索区内）；③ 解析 0x4d6dd0
  375KB 静态区排除。

## 7. 其余未解项

| 项 | 现状 | 下一步 |
|---|---|---|
| u14/u16/u17/u18/u42/u47(bit4-6)/u39/尾24B/g/h | 原值可读，语义未定证（u39 在 E5.2 有 13 格变化=动态小计数） | 与游戏本体反汇编（Plot 序列化函数）对齐；或更多差分档 |
| 奇观 52B 附加数据 | 常量 0x1d2f95b3/0x4344acef + 计数，结构未解 | 与 Constructibles 实例 id 对账 |
| FeatureLayoutCache 1.16MB | 子数组头 `[5][hash][0][3404][74][3404]` 可读；E1 变化 20B 未解 | 差分定位 148B 周期段的索引对象 |
| 0x4d6dd0 375KB 静态区 | `[0x40ae9bb5][1][1][0xa00048]` 头 + u16 对（含 (9,45) 等疑似坐标对），尾部 20B 记录 | 疑渲染网格/邻接缓存，优先级低 |
| 字符串调色板 7 段 ×41KB | 前缀共享压缩表（"UIDL"/"ave"/"Turn"…），每玩家一份 | 与地形无关，未啃（按任务允许跳过） |
| 尾 24B 区间对假设 | 与 Areas(120)/Hemispheres(96)/Landmasses(32) 容量数值吻合，但未做 id 级对账 | 解析三个容器逐项对名 |

## 8. 工具与产物

- `tools/terrain.py`：内置 187 名游戏词表（XML 提取，地形/生态/大陆名不落盘必须内置）+
  运行时 grep body 明文补充；自定界记录解析；输出宽高自检、逐格字段、资源坐标表、
  PlotsRevealed 计数（归属未定证）、未解字段原值。
- 产物：`/tmp/scratch/e0_terrain.json`（E0 全量）；`e1/e2/e52/modern_terrain.json` 为回归验证档。
- 已知怪癖：最后一条记录（plot W*H-1）只有 49B 无尾 24B；记录解析不依赖统一 stride。
