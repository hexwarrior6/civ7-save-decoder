# 文明7 .Civ7Save 存档格式逆向笔记

> 2026-11-08 逆向完成。版本 1.4.11（macOS）。所有结论均经过交叉验证。

## 1. 容器结构

```
[4B] 魔数 "CIV7"
[...明文头部区块...]                    ← 头部 chunk（见 §2）
[4B] 00 00 01 00                       ← 压缩数据标记（65536 块长）
[...] zlib 压缩数据                    ← 游戏状态主体（见 §3）
[4B] 01 00 00 00                       ← 块结束标记
[...尾部数据...]
```

- 压缩数据 = `[u32 LE 块长][块数据]` × N 的 zlib 流，最后一个 u32 ≤ 1 为终止标记
- Python 解压：`zlib.decompressobj()` 逐块喂入，最后 `d.flush(zlib.Z_SYNC_FLUSH)`
- 解压后约 20-24 MB 的游戏状态数据库

## 2. 头部 chunk 格式

解压前的明文头部是 5 个区块组（g1-g5），每组：`[u32 数量][chunk×N]`。

chunk 格式：`[marker u32][type u32][pad u32][data]`

| type | 含义 |
|---|---|
| 2 | UTF-8 字符串 |
| 8 | Number32 |
| 29 | ChunkArray（嵌套数组） |
| 30 | NestedArray |

关键 marker（字节序注意：`9d2ce6bd` 在 LE u32 下 = 0xbde62c9d）：

| marker | 含义 |
|---|---|
| 0xbde62c9d | GAME_TURN（时代内回合） |
| 0xe8615afe | GAME_DATE（本地化日期字符串） |
| 0xd0c68484 | GAME_AGE |
| 0x0ffb8cc1 | LEADER_NAME |
| 0x769740de | CIV_NAME |
| 0x7a9ca019 | CIV_LEVEL（FULL_CIV/CITY_STATE） |
| 0xd45f8328 | PLAYER_TYPE（3=人类, 1=AI） |
| 0x0eed6e29 | ALIVE_FLAGS（偏移+8, 1=存活） |
| 0xdef62d9b | TEAM_ID |

## 3. 解压后主体

解压后的数据 = **FXSBLKED 分块属性包** + **数据库定义快照（XML 同构）** + **名人堂（GAME_SUMMARY）**。

### 3.1 名人堂（GAME_SUMMARY）

存档中有 2-4 处 `GAME_SUMMARY` 标记。第 2 块包含：

**A. 城市名注册表**：`[04 00 00 00]['City'][valueLen][LOC_CITY_NAME_X]` × N 的连续键值对——按建城顺序排列全部定居点名池代号。

**B. 回放数据集**（`REPLAYDATASET_*`）：24 个数据集，记录每回合×每文明的历史数据。两种编码：
- 大数据集（科技/文化/金币/分数）：13 字节头（含 u64 记录数）+ 12 字节记录 `(col=文明slot, row=回合, val=u32)`
- 小事件数据集（宣战/夺城/失城/击杀）：12 字节记录 `(256, 文明, 回合)` 或 `(文明, 回合, 256)`
- 所有数值 = **×256 定点数**（除以 256 得真实值）

可用数据集：SCIENCEPERTURN / CULTURE / TOTALGOLD / SCOREPERTURN / TOTALWARSDECLARED / TOTALCITIESCAPTURED / TOTALCITIESLOST / TOTALUNITSDESTROYED / TOTALWONDERSBUILT / TOTALCITIESBUILT / TOTALDISTRICTSBUILT / TOTALBUILDINGSBUILT / TOTALCOMBATS / GREATPEOPLEEARNED 等。

**跨存档一致性**：数据集是时代内累计历史，同一局的不同存档逐字节一致（已验证），新存档只是延长回合轴。

### 3.2 城市详细记录

名人堂块中还包含每座城市的**建筑/改良/奇观完整清单**（按建造顺序），结构：

```
[04 00 00 00]['City'][valueLen][LOC_CITY_NAME_X]    ← 城市名
[07 00 00 00]['Founder'][...]                        ← 建立者
[0b 00 00 00]['TurnFounded'][...]                    ← 建造回合 ×N
[14 00 00 00]['BuildingsBuiltByType']
    [04 00 00 00][u32]                               ← 未知字段
    [12 00 00 00]['BUILDING_X']                      ← 建筑类型
    [01 01 00 00 00 00 00 00 00]                     ← 固定尾部
[14 00 00 00]['WondersBuiltByType']
    [valueLen]['WONDER_X']
...
```

**已知问题**：相邻城市记录之间的分隔符格式未完全破解——部分城市的记录没有独立的 `City` 键，导致逐城归属在连续段落中混淆（多城数据堆叠）。

**变通方案**：用 plot u32 值（`struct.pack('<I', plot)`）在 GAME_SUMMARY 区外全文搜索引用次数，确认定居点存活。

### 3.3 城市名池

城市名 = `LOC_CITY_NAME_<文明>_<序号>`，从游戏本地化文件翻译：
```
/Applications/CivilizationVII.app/Contents/Resources/Base/modules/age-<时代>/l10n/zh_Hans_CN_Text.xml
```
每个文明的城名按序号对应名池（GREECE1=雅典, GREECE2=斯巴达...）。

### 3.4 地理坐标系统

- **plot = y × 74 + x**（行优先，本例地图宽 74 格；不同地图尺寸的 W 需重新标定）
- 列号与游戏内东西方位直接对应；行号**上下颠倒**（row_real = map_height - 1 - row_decoded，另有面板边距偏移）
- 校准方法：用游戏内小地图截图 + PIL 采样成网格，与存档解码城市做势力聚类对齐
- Civ7 地图东西环绕（圆柱形）、南北不环绕

### 3.5 遗产路径 VP 计分

DB 定义区含 `LEGACY_PATH_*` / `VICTORY_*_SCORING` 定义，字段 `[VP N][VICTORY_名字][REQSET_...][条件=1]`。

实测：`VICTORY_EXPLORATION_MILITARY_DISTANT_CONQUEST_SCORING` = 每次远洋征服 4 VP；科技路径 `YieldNeeded=40`。现代军事路径有意识形态变体（对立意识形态征服得分更高）。

### 3.6 政策/传统效果

DB 定义区含全部传统/政策的修改器定义，格式 `[len][修改器名][hash][type][键值对...]`。例：

```xml
LEVIES_MOD_UNIT_PURCHASE2: Percent=25, UnitTag=UNIT_CLASS_COMBAT  ← 战斗单位购买-25%
MOD_SHIPYARD_UNIT_PRODUCTION: Domain=DOMAIN_SEA, Percent=10       ← 船坞海军产能+10%
```

**注意**：玩家"当前生效政策"是运行时哈希态，字符串层读不到。游戏本体数据文件在磁盘上明文可读：
```
/Applications/CivilizationVII.app/Contents/Resources/Base/modules/<时代>/data/*.xml
```

## 4. 游戏机制备忘（wiki + 游戏数据交叉核实）

- 时代过渡：1 首都（城市）+ 其余全部变回城镇；转城 = `PROJECT_CONVERT_TOWN_TO_CITY`，费用 = 800 + 1000×已有城市数 − 50×镇人口（下限200、上限5000），**抢来的镇 ×2**
- 城镇重心：7 人口可选，**选定后锁到时代结束**（只能在所选和"成长"之间切）；"城市中心"= 每城区+1科技+1文化
- 指挥官：跨时代保留（经验晋升全在），每个指挥官保护最多 4 个打包单位免于更替删除
- 海军单位：定居点需 ≥1 水格 + ≥1 水系建筑（港湾/渔港线）
- 单位购买价随时代倍率放大

## 5. 已知未解

- FXS 属性包的二进制值结构（VariantValue 序列化）——阻塞了城市人口、单位、外交态度的逐城读取
- 名人堂详细记录的分隔符——多城数据堆叠问题的最后一步
- 玩家当前生效政策列表（运行时哈希态）

## 6. FXS 属性包（FXSBLKED / DelineatedData）——已破解

> 2026-11-09 逆向完成。方法：游戏本体二进制（CivilizationVII，带完整 C++ 符号）反汇编
> `Data::VariantValue::Serialize`、`Serialization::DelineatedData::*`、`Crypto::CRC::CalcString`
> 等函数，逐条与存档字节对照验证。

### 6.1 字段名哈希（MakeKey）

**CRC32**，参数：多项式 `0xEDB88320`（标准 CRC-32），初值 `0xFFFFFFFF`，**无终值异或**，
输入 = 字段名的 ASCII 字节（camelCase，如 `CurrentFood`、`locInstigatingPlayerWarName`）。

验证对：`"Name"→0x01ee2ec7`、`"ID"→0xee2c9cc5`、`"GAME_TURN"→0xbde62c9d`。
（社区猜的 FNV 与全大写命名均错误。）

### 6.2 VariantValueType 类型枚举（从二进制类型表整体提取）

| 值 | 类型 | 值 | 类型 |
|---|---|---|---|
| 0 | None | 14 | VariantObject |
| 1-13 | Bool, Char, Char16, Int8, UInt8, Int16, UInt16, Int(4B), UInt(4B), Int64, UInt64, Float, Double | 15-20 | Pair{Int16,UInt16,Int32,Int64,Float,Double} |
| 27 | VariantMap | 21-26 | Triplet{同上} |
| 28 | VariantVector | 29 | TypedVariantMap |
| 30 | TypedVariantVector | 31 | TypedVariantVectorMap |
| 32 | GUID | | |

**0x400 修饰位**（`base | 0x400`）语义（来自 `IsBlockType` / `IsBlockTypeWithSize` /
`HasTerminator64` 反汇编）：

| 标签 | 磁盘编码 |
|---|---|
| 0x400 / 0x403 | 尺寸块：`[u32 size][size 字节]` |
| 0x402 | 字符串：`[u32 len][bytes][u64 终止符]`，终止符 = ASCII `"FXSBLKED"`（8 字节） |
| 0x405 | 带终止符块 |
| 0x407 | **FixedPoint<8>**：u32 raw，真实值 = raw/256（金币/影响力/产量全用此编码） |
| 0x400,0x401,0x403,0x404 | "块类型"（可含嵌套内容） |

**FXSBLKED 魔数真相**：不是块头，而是 `Terminator64` 的默认值 = u64 `0x45444B4C58534246`
= ASCII "FXSBLKED"，写在 0x402/0x405 类型值之后。社区工具的"marker→FXSBLKED→+8→值"
导航本质是跳过前一个字符串值的终止符。

### 6.3 块（TypedVariantMap 序列化）

```
块 = [u32 hash?] [u32 1] [u32 -1] [u32 1] [u32 1] [u32 count]
     [count × (u32 hash, u32 type)]        ← schema 条目
     [values 按条目顺序]                    ← 值区
```

- hash 可省略（根块），`hash=1` 视为根
- hash = 块对象名的 CRC32（如增长对象 `0x635c5324`）
- 块间无分隔符；前一个字符串值的 FXSBLKED 终止符天然分隔

### 6.4 已验证的运行时数据（AutoSave_02_0004，回合4）

**金币/影响力**（社区工具的标记导航，已验证）：
`[GOLD_MARKER 0x37991e23] → 下一个 FXSBLKED → +8 → u32 FixedPoint<8>`。
6 个主要文明读出 8585/1835/987/780/798/477，人类玩家 8585 + 面板收入 385.9 = 8971 ✓。

**城市增长记录**（44 个定居点全解析，块 hash `0x635c5324`）：
字段 = CurrentFood / CurrentStarvation / GrowthType / MigrationCityID / ProjectType /
TurnLastNotifyStarving / NextGrowthFoodThreshold(Base) / UnitTypeFoodMods /
AllUnitTypesFoodMod / PercentGrowthAfterWorkerPlacement / PercentGrowthAfterRuralPlacement /
OverGrowthCount / TurnLastGrowth / lastTurnConsidered / NextGrowthFoodTresholdDiscount。

雅典（第一个块）CurrentFood = 42214/256 = **164.898 = 面板 339.5 − 174.6**（存档在回合4
开始时点，面板在回合中，差值 = 一回合食物）✓。注意部分 size-4 块存的是递增引用索引
（105423..105428 连号）而非数值，需按字段区分。

**城市运行时记录**：`[u32 keyLen]["LOC_CITY_NAME_GREECE1"][FXSBLKED]` 后紧跟值序列：
雅典 = `[4][38]`（人口）→ `[4][0]` → 6 个引用索引 → 嵌套对象……与 GAME_SUMMARY 的
城市名注册表同构。

### 6.5 回放数据集（GAME_SUMMARY 内，已完整破解）

```
[u32 keyLen]["REPLAYDATASET_X"][u32 valLen]["LOC_HOF_GRAPH_..."][u32 0]
[u8 1][u8 1|2][u8 0][u8 0][u8 0][u64 recCount]     ← 13 字节头
[recCount × (u32 col, u32 row, u32 val)]            ← col=文明slot, row=时代内回合
```
- 数值 = FixedPoint<8>（raw/256）
- 回合1存档 recCount=0；回合4存档 recCount=32 = 行1(5)+行2(13)+行3(14) ✓
- TOTALGOLD 行1 = (1,9000)(2,688)(3,623)(4,1221) 与金币标记逐一吻合 ✓

### 6.6 待细化（已知未知）

- size-4 块中"引用索引"与"FixedPoint 值"的区分规则（部分字段存句柄）
- NextGrowthFoodThreshold(411.97) 与面板"需要食物 4614"的换算关系
- 值区字段与 schema 条目的精确对位（部分块存在额外字节）
