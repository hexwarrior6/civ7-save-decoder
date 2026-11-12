# BatchA 收尾杂项 — ①资源库存 ②探索迷雾位图 ③地形标志位语义

> 2026-11-12。三件活的完整记录。验证档：E0/E1/E2/E5.1/E5.2/E6/E7（远古同局）+ MODERN
> （AutoSave_02_0027，另一局）。工具：`tools/resources.py`（新增）、`tools/terrain.py`
> （迷雾 + 标志位扩展）。中间分析脚本在 /tmp/scratch（flags_an.py / flags_nb.py / flags_b.py）。

## 1. 玩家资源库存（工具 tools/resources.py）

### 1.1 定位与块结构

- 每玩家 1 个资源库存块，hash `0x926896f2`（字段名 "Resources"，16 字段），块锚
  `[926896f2][1][-1][1][1][16]`。E0 31 块（0x463227 起，紧随各玩家实例块之后），
  MODERN 19 块（死者块消失，与 PlotsRevealed 块同规律）。
- 归属 slot = 最近前置玩家实例块（0x00000003/56f）的 ID 字段（复用 units.py 定位）。
- 字段：Properties(str) / **AvailableResourceCounts** / ResourceCountModifier /
  CityAssignedResourceCounts / **ResourceClassCounts** / UnassignedResourceYieldBonus /
  **Assignments** / TotalResourceCount / UniqueResourceCount / ImportedResourceCount /
  DistantLandsResourceCount / UnassignedResourceCount / YieldPerImprovedResource /
  TurnLastConsidered / TurnLastReceived / NoTreasureFleetsFromResourcesCounter。

### 1.2 计数节点（AvailableResourceCounts）

- `AvailableResourceCounts = [0x80000000|55][55 × u32 句柄]`（E0 全部 31 块 n=55 恒定）。
- 每句柄指向**对象图节点**：`[tag][id][hA=数组下标][t2=3][hB=资源定义hash][载荷 FP8][尾=id]`。
  **hA==数组下标** 是强签名：E0 31 块 × 55 = 1705/1705 全命中（0 坏）；MODERN 1045/1045。
- 零库存 = 空载荷节点；非零 = 4B FP8（raw/256）。E0 六国有库存玩家各 1-2 种（1.0/256 定点）。

### 1.3 资源名序表（55 项）

- body DB 定义区有一条 55 项 RESOURCE_* CRC 序表，定义序 = 数组下标序：E0 @0x165e5、
  MODERN @0x15b61（两档逐项相同）。名字来源 = body 明文 grep + LOC_RESOURCE_*_NAME 剥前缀
  （units.py 同款技巧）+ `_DISTANT_LANDS` 变体推断（RESOURCE_GOLD_DISTANT_LANDS 只以
  LOC_RESOURCE_GOLD_NAME 共享落盘，拼不全）。
- 仲裁：候选序表经「类别和==ResourceClassCounts」「assignment plot 地图资源∈非零库存」双重
  交叉自检（0 失败且 ≥1 有效检查才采纳），平手取非字典序者。全败时回退内置 FALLBACK_ORDER
  （与 E0/MODERN 实测一致；换游戏版本需复核，输出 notes 如实标注）。

### 1.4 类别计数（ResourceClassCounts）

- 远古档（E0-E7）= **3 句柄**，序 = [BONUS, CITY, EMPIRE]（内置自游戏本体
  base-standard/data/resources.xml + resources-v2.xml）。交叉定证：E0 slot0 = WOOL(BONUS)+
  HARDWOOD(EMPIRE) → [1,0,1]；slot1 = WOOL+FLAX(CITY) → [1,1,0]。31 块类别和全对账通过。
- MODERN = **4 直接 FP8 标量**（无句柄），4 值之和 == 总库存（19/19 对账），但与 XML 类别
  映射的逐类和不符 → **逐资源类别疑随时代变化，4 类语义未定证**，输出按 class0-3 原值。

### 1.5 Assignments（资源分配）

- `Assignments = [count][count × 20B]`，每条 `[hdr 0x0016ffff][plot=y*W+x][amount][u32][u32]`。
  资源种类由 plot 上的地图资源决定（terrain.py 交叉）。
- 验证：E0 六国 11 条 assignment 全部满足「地图该格资源 == 库存中该资源且 amount ≤ 库存量」
  （11/11）；MODERN 191/191。**首都邻近合理性**：E0 六国 11 条 assignment 距各自首都
  ≤3 格（俄 489=(45,6) ↔ HARDWOOD(46,4)/WOOL(46,7)）。

### 1.6 自检与未解

- 输出 self_check：hA 签名 1705+1045 全命中；sum(counts)==TotalResourceCount 31/31+19/19；
  非零种数==UniqueResourceCount 同上；类别和==ResourceClassCounts（3 类档）同上；
  assignment 交叉 11/11 + 191/191。任何一项失败均如实入 notes，不静默。
- 未解：Assignments 尾部两个 u32（0x0001000X/0x0001ffff/ffffffff）；CityAssignedResourceCounts
  55 句柄节点 = [u16 1][u32 列表句柄]，逐城数量列表节点结构未解；UnassignedResourceYieldBonus /
  YieldPerImprovedResource 7 项原值（疑产量 bonus，常全 0）；ResourceCountModifier 55 句柄
  （hA 全命中但未对账，疑全 0）。

## 2. 探索迷雾位图（已破解，terrain.py extract_explored）

### 2.1 记录格式

- 每玩家一条 **3404B 字节数组（0/1，1=已探索）**，位于 Plots 块之后 / 玩家实例区之前的
  **视野大区**（k0 记录 @0x3364e9，数据段 @0x3364fe = 记录+21B；步长 ~0x92D9/玩家）。
- 记录头（21B）：`[u32 玩家id][u32 2][u32 玩家id][u32 popcount][u8 flag][u32 3404]`。
  E0 k0 实测头 = `00000000 02000000 00000000 c2000000 00 4c0d0000`：id=0、pc=0xc2=194
  （==数组 popcount ✓）、flag=0。flag=1 的记录不写数据（pc 恒 0，以数组为准）。
- 玩家 id 集 = 0..N-1 + 63（E0 31 个、MODERN 19 个；63 = 第 31 玩家/蛮族位）。
- **重要更正**：phase6 标注的 "FeatureLayoutCache（0x3364e9 起 1.16MB）" 实为该视野大区的
  首个结构 = 迷雾位图；phase1 §5 的区域划分需按此重读。

### 2.2 证据链（全部落盘可复现）

1. **静态性**：E0==E1==E2==E6==E7 全 31 玩家 3404B 逐字节一致（开拓者移动/退档重存均不改
   迷雾——已探索区内移动不重 fog，符合"探索层"而非"可见层"语义）。
2. **动态同步**：E0→E5.1 每玩家新增 bit 数 == b6be9ade PlotsRevealed 增量，30/31 精确相等
   （唯一例外 k4：+23 vs +18）；E5.1→E5.2 同构 30/31（k0 +3 vs 0）；且 E0→E5.1 无任何
   bit 丢失（单调不减）。
3. **单位锚点**：E0 69/69、MODERN 186/186（有效位）单位落点全在本玩家已探索格内
   （MODERN 其余 18 单位 plot=-749925 为无效占位，非真实坐标）。
4. **连通性**：各玩家位图 = 围绕首都的连通区域（k0 194 格 8 邻连通，bbox 含首都）；
   城邦小 blob 138/148 等。
5. **k=63**（蛮族位）：247 格散布全图 bbox [6-73]×[5-44]，不包含任何单一玩家集合 →
   疑蛮族单位游历揭示或系统记录，语义未定证。

### 2.3 与 PlotsRevealed 计数的关系（未解部分）

- 城邦 popcount == PlotsRevealed 精确相等（E0 21/31、MODERN 小文明逐个精确：105/105、
  53/53、94/94…）；主要文明 popcount > PlotsRevealed（E0 +30~43，MODERN 3173 vs 785）。
- 猜测：PlotsRevealed 只计本玩家自探格，位图含他人/城邦共享视野——未定证；不影响位图本体。
- MODERN 三个玩家（k5/k16/k17）PlotsRevealed=0 但位图 3022/352/481 —— b6be9ade 块缺失或
  归属错位的死玩家。

### 2.4 未解（下一步）

- 每玩家 0x92D9 步长中除 3404B 迷雾外的 ~34KB：疑含"当前可见层"/单位可见位图，未啃。
- PlotsRevealed 计数的精确语义（自探 vs 共享）。

## 3. 地形标志位 u14~u47（E0 全图 3404 格统计 × 两图交叉）

### 3.1 已定证（写入 terrain.py 输出 named 字段）

| 字段 | 语义 | 证据 |
|---|---|---|
| **u42** | 地形游戏分类：255=水域/山/可航河，0=丘陵，1=平地裸，2=平地湿润/植被特征 | OCEAN1485+COAST690+MOUNT134+NAVR48=2357 全 255；HILL 184 全 0；FLAT 863 精确二分 428(裸,特征全 NONE)+435(特征全集=RAINFOREST/TAIGA/FOREST/SAVANNA/STEPPE/OASIS/MANGROVE/WATERING_HOLE/MARSH/四类FLOODPLAIN_MINOR/BOG=湿+植被类)；MODERN 同构 |
| **u47.bit3** | **不可通行**：FEATURE_ICE(268) ∪ TERRAIN_MOUNTAIN(134) ∪ {ULURU,THERA×4} | E0 407 格；MODERN 428 = ICE∪MOUNT ∪ {THERA×4, GRAND_CANYON×4}（ZJJ 逐格=1）；BARRIER_REEF=0（可通行）；两图 6 种奇观全验证 → 比旧结论"冰雪"更准 |
| **u47.bit4/5/6** | u18.bit3/1/2 的逐格镜像 | 集合相等 135/135、128/128、121/121（E0 精确） |
| **u17** | 地图大区 id：0=岛群(多 blob)，1/2=连续大陆区，255=外洋 | E0 blob 5/1/1（0=94+82+68+50+15 岛群）；MODERN 同构 6/1/1，255=外洋(含 4 碎格)；THERA 两图均在 region2（Distant Lands 疑指 region2） |
| **u16** | 岛群标志：2 ⟺ u17==0（region0），否则 0 | 两图逐格精确（309/309、308/308） |

- 输出新增：每格 `terrain_class` / `region_id` / `island_region` / `impassable`；
  summary 新增 terrain_class / region_id / island_region_plots / impassable_plots。

### 3.2 保持 raw + 特征画像（未定证）

| 字段 | 原值分布画像 | 排除的假设 |
|---|---|---|
| **u14** | 平滑静态场：空间自相关 r=0.81（陆-陆邻居 6678 对）；仅陆地+湖非零（0 ⟺ 非湖水域）；值域 0-1100+，654 个不同值；与 elv 相关 r=-0.07（独立于高度场） | 非高度第二通道（不相关）；疑地图生成气候/渲染噪声，语义未定证 |
| **u18** | 6 位掩码，每 bit 121-135 格；bit 集合富集海岸邻接(74-86%)、资源邻接(60-68%)、湖邻接；全图 22.6% 格非零 | **邻居方向位假设排除**：odd-r/even-r 两约定 × 6 方向 × "邻居是山/水"全试，最高 12/135（随机级）；≠河流边位 |
| **u39** | 半静态计数 0-30：E0 338 格非零（均值 ~3.7），值域 1-6 为主；**建城区被覆写**（E0→E5.2 仅 13 格变化，全部=u43/u45 0→id 的新建城区格，新值 1-5）；高值集中自然奇观（THERA 30 / KILI 23 / GC 25 / TORRES 22，但同奇观部分格 0）；海/岸恒 0（690 COAST 全 0） | 非特征移除计数（13 格特征均未变）；非年龄/回合戳（旧值不随 +10 回合增长）；非可见性计数；疑"地图生成期值+建城覆写"，精确语义未定证 |
| **尾 24B g/h** | g=6 位掩码（0-63，159 格非零），h 恒 6 例外 16-37（157 格）；g/h≠0 格富集 navr 邻接(34% vs 基线)与资源邻接(66%) | **h=河流 id 排除**：48 navr 中 37 个 h=6；岸邻 h 一致率仅 12-14%。假设未定证 |

### 3.3 方法备忘

- 统计脚本对 3404 格逐位做 取值分布 × {地形/生物群系/大陆/特征/资源/湖/海冰/奇观/距城}
  交叉表；方向类假设用 odd-r/even-r 两套六邻约定置换检验（odd-r 经河链连通度确认为正确
  网格：navr 度分布 {0:9,1:20,2:19} vs even-r {0:19,1:19,2:9,3:1}）。
- 动态判据：E0/E1（移动）/E0→E5.2（城建）/MODERN（另局长局）三层差分分离静态与动态字段。

## 4. 未解清单（本批遗留）

1. u14 / u18 / u39 / 尾 24B g-h 的精确语义（原值与画像已存，见 §3.2）。
2. 资源：Assignments 尾 u32、CityAssignedResourceCounts 列表节点、MODERN 4 类类别语义。
3. 迷雾：PlotsRevealed 精确语义；视野大区每玩家 ~34KB 其余结构；k=63 位图归属。
4. 0x4d6dd0 375KB 静态区、字符串调色板（phase6 遗留，未动）。
