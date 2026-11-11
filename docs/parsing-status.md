# 解析进度详情

> 按存档物理顺序逐区域逐字段的解析状态。更新于 2026-11-12（Phase4 外交完成）；基础数据基于 AutoSave_02_0001.Civ7Save（现代时代 t1）与远古档 E0/E1/E5.1/E5.2。

## 存档物理结构

```
.Civ7Save 文件 (~5MB 压缩)
├── 明文头部 (~70KB, 未压缩)
│   ├── 元数据（时代/回合/日期/速度/地图/难度/GUID）
│   └── 文明名单（领袖/文明/人类AI/存活/队伍）
├── 压缩标记 (6字节: 00 00 01 00 78 9C)
├── zlib 压缩体 (~24MB 解压后)
│   ├── 数据库定义快照 (~15MB)
│   │   ├── 时代模块（文明/建筑/单位/政策/传统规则）
│   │   ├── 胜利条件（四条路径 VP 计分）
│   │   ├── 政策/传统修改器
│   │   ├── 资源定义
│   │   └── 危机定义
│   ├── 名人堂 GAME_SUMMARY (~1MB)
│   │   ├── 城市名注册表（42 条，建城顺序）
│   │   ├── 创始人记录
│   │   └── 建造编年史（全游戏逐建筑逐改良）
│   ├── 运行时城市记录 (~0.1MB)
│   └── 运行时属性包 (FXSBLKED, ~8MB)
│       ├── 定居点详情
│       ├── 单位
│       ├── 外交关系
│       ├── 遗产路径进度
│       ├── 宗教传播
│       ├── 幸福度
│       └── 地形/地图
└── 尾部标记 (8字节)
```

## 逐区域解析状态

### 1. 明文头部 — ✅ 100%

| 字段 | 状态 | 备注 |
|---|:---:|---|
| 时代（AGE_MODERN 等） | ✅ | |
| 回合（GAME_TURN，时代内回合） | ✅ | |
| 日期（本地化字符串，如"公元1750年"） | ✅ | |
| 游戏速度 / 地图尺寸 / 难度 / 规则集 | ✅ | |
| 游戏 GUID（同局标识） | ✅ | |
| 文明名单（领袖/文明/人类AI/存活/队伍） | ✅ | 全部 slot 读取 |
| DLC/模块列表 | ✅ | |

### 2. 名人堂 GAME_SUMMARY — ✅ 核心已解 / ⚠️ 归属未完

| 子区域 | 状态 | 备注 |
|---|:---:|---|
| 城市名注册表（City→名字+归属+坐标） | ✅ | 42 条全部解析，plot = y×74+x |
| 城市名翻译（loc key → 中文名） | ✅ | 通过游戏本体 l10n XML 对照 |
| 回放数据集（24 个 REPLAYDATASET） | ✅ | 科技/文化/金币逐回合×逐文明 |
| 战争/夺城/失城/击杀事件 | ✅ | 12 字节记录 (256,文明,回合) |
| 奇观/建城/城区/建筑累计 | ✅ | t1 快照 + 增量 |
| 建造编年史（全游戏逐建筑逐改良） | ⚠️ | 条目全部可读，逐城归属的分隔符未破解 |
| 创始人记录（Founder 字段值） | ⚠️ | 键定位✅，值结构未解 |

### 3. 数据库定义快照 — ✅ 按需可查

| 子区域 | 状态 | 备注 |
|---|:---:|---|
| 胜利条件（四条路径 VP 计分定义） | ✅ | 军事4VP / 科技40产量 / 意识形态变体 |
| 政策/传统效果数值（如 Levies -25%） | ✅ | 修改器名+数值+作用域 |
| 资源定义（107 种） | ✅ | 煤/石油/大理石/银/丝绸... |
| 危机定义（探险时代三种） | ✅ | 瘟疫/宗教/革命 |
| 单位/建筑定义 | ⚠️ | 按需可查，未做全量索引 |
| 意识形态定义 | ✅ | 现代军事计分变体 |

### 4. 运行时属性包（FXSBLKED）— ✅ 格式已破解 / Phase1 通用遍历器完成

> 2026-11-09 通过游戏本体二进制反汇编完全破解序列化格式（详见 save-format.md §6）。
> 哈希 = CRC32（0xEDB88320, init -1, ASCII）；类型枚举 33 个；块 = [A][1?][-1][1][1][count]+条目+值；
> 0x402=字符串（[len][bytes][pad4][FXSBLKED 终止符]）、0x407=FixedPoint<8>、0x400/0x403=[size][bytes]。
> **Phase1（2026-11-09）**：通用块遍历器 `tools/blockwalk.py` 完成；E0 实测 376 块完整解析、
> 值区与 schema 100% 对位（U3 关闭）；E1/E0 差分 20 区间全部定位（开拓者位置/移动力/视野/HP）。
> 详见 docs/notes/phase1-blocks.md、phase1-unknowns.md、phase1-diff-e1e0.md。

| 子区域 | 状态 | 备注 |
|---|:---:|---|
| 金币/影响力（每文明） | ✅ | FP8；E0 GoldBalance=7680→30.0 ✓顶栏 |
| 城市增长（17 字段×每城） | ✅ | CurrentFood=40.0 ✓面板；阈值字段=句柄（U2 更正）；⚠️ 现代档 44 块 CurrentFood=0 疑点见 phase2-cities.md §7 |
| 城市实例块（29 字段：人口/位置/归属） | ✅ | HighestPopulation=[4][6] ✓人口6 |
| **城市人口分项（Phase2）** | ✅ | Rural/Urban/Worker 句柄→对象图节点 FP8；44/44 城 乡+市+专==总数（雅典 38=17+20+1 ✓圣彼得堡 6=4+2+0 ✓） |
| **城市归属 OwnerIDHistory（Phase2）** | ✅ | [count×(slot,1,turn,hash)]；44 城归属分组零冲突；4 种易主 hash 细分未解 |
| **城市提取器 tools/cities.py（Phase2）** | ✅ | `python3 -I tools/cities.py <body.bin> <out.json>`；名字/坐标/人口/增长/归属/连接数；详见 docs/notes/phase2-cities.md |
| 单位块（47 字段：位置/朝向/视野/HP） | ✅ | Location blob8=(x,y)、MovesRemaining FP8=3/3 ✓、Damage=0→HP100 |
| 单位命令缓存块（14 字段镜像） | ✅ | Location/MovesRemaining/HasMoved 与单位块一致 |
| **单位提取器 tools/units.py（Phase3）** | ✅ | `python3 -I tools/units.py <body.bin> <out.json>`；类型/归属/位置/HP/移动力/朝向/has_moved/经验全解；E0 69 单位、E5 89 单位 0 解析失败；详见 docs/notes/phase3-units.md |
| **单位组语法（Phase3）** | ✅ | 玩家实例→Units 块→Units 容器=N×[组前缀+实例 47f+战斗/移动/宗教/经验/奖励子块]；Formations 容器=每单位 1 条 14 字段命令记录 |
| **单位类型 Type CRC 反查（Phase3）** | ✅ | DB 快照 grep UNIT_* + _NAME 剥离 + 游戏本体 XML 补查（UNIT_SLINGER）；SCOUT/SETTLER/WARRIOR/MIGRANT/GALLEY/SLINGER 全命中 |
| **单位归属（Phase3）** | ✅ | 实例无 Owner 字段；归属=最近前置玩家实例块 ID（=slot）；E0 31 玩家 0..30+63，24-29 死亡城邦无单位 ✓ |
| **HasMoved 语义（Phase3）** | ✅ | =本回合已消耗移动力；E0 64/69 True=AI 已行动、人类+刚出厂=False；记录镜像移动力 335/357 一致 |
| **外交关系块组（Phase4）** | ✅ | 78f 影响力块(K=00000005)+15f 余额块(K=7d74610f)+18f 全局战争块(K=dced693c)+13f 修正块+16f 部落块+3f 协议块，每玩家定位完毕 |
| **开放边界状态位（Phase4）** | ✅ | HasOpenBordersFrom=64×u8/玩家块，bit[X]=1 ⇒ X 对我开放边界；E2 差分唯一变化 slot0.bit[4]=1（诺曼）✓；宗主单向/大文明双向（现代档 11 对）✓ |
| **影响力余额（Phase4）** | ✅ | DiplomacyBalance FP8 直读：E0 slot0=80.0 ✓顶栏；E2=55.0=80−25（开放边界标价 25）✓；城邦=0 |
| **战争/和平矩阵（Phase4）** | ✅ | AtWar 三角阵 [2016][C(64,2)×8B]；E0/E2 实体 0-29 之间全部和平 ✓；行 40-57 条目 + WarInitiator=63−行 模式见 phase4 §3.2（语义未定证） |
| **同盟/友谊/关系分（Phase4）** | ✅ | IsAllied/HasDeclaredFriendship/IsInDefensivePact 全 0（无同盟）；RelationshipLevel=64×FP8 对称（俄-诺 25.0、阿-诺 11.0、波-法 3.0）；5 级等级名阈值未标定 |
| **外交修正值（Phase4）** | ✅ | 13f 块 DiplomaticModifiers 等 6 数组=[64][64×u32]，E0/E2 全 0 |
| **外交事件表（Phase4）** | ✅/⚠️ | ActiveDiplomacyEventsV2=[count][事件]：E2 追加 A=12=开放边界 ✓；其余 type_a→动作名未标定 |
| **外交关系提取器 tools/diplomacy.py（Phase4）** | ✅ | `python3 -I tools/diplomacy.py <body.bin> <out.json>`；E0/E2/MODERN 0 解析失败；详见 docs/notes/phase4-diplomacy.md |
| 单位经验 Level | ❌ | Experience=直读 Int ✓；Level=blob4 句柄（~138k）对象图无标量节点，公式未解 | |
| 玩家实例块（56 字段） | ✅ | ID/IsAlive/Civilization 等 |
| 引用句柄 vs 数值（size-4 块） | ✅ | U1 关闭：按字段语义+连号+图区间二次确认，见 phase1-unknowns.md |
| **对象图节点语法（Phase2 部分破解）** | ⚠️ | 节点=[tag][id][hashA][t2]…[id-again]；标量节点(FP8)/零值节点/引用载荷已验证；流级语法与节点 class 语义未解 |
| 0x402 容器形（Properties/Components 子流） | ⚠️ | [len=1] 无终止符+子块流；子块可遍历，容器边界未定 |
| 城市产量明细（七项每回合值） | ❌ | Yields[7] 等为修正对象 DAG 句柄；无落盘原值（174.6/9.0 全文无）；公式未解 |
| 幸福度分档值（"愉快"0~20） | ❌ | Unhappiness/SuplusHappiness=句柄；图中无 0~20 标量（值域 1–10） |
| 建筑清单（逐城） | ❌ | Constructibles 0x402 容器未定界；建造编年史逐城归属分隔符未解 |
| 增长阈值面板值（149/4614） | ❌ | 运行时由句柄对象计算，落盘无原值；公式未还原（U2） |

### 5. 已知的格式怪癖

- 名人堂在新时代 t1 只注册部分定居点（42/48），别误判为城市被毁
- 回放数据集跨存档逐字节一致，新存档延长回合轴
- 数据集数值 = ×256 定点数
- 建造编年史中相邻城市记录无分隔符，需靠其他方式切分
- 地图东西环绕（圆柱形），南北不环绕
- 换时代时城市可能被新文明名池重新登记

## 突破方向

**Phase2 后剩余瓶颈（按价值排序）**：

0. **单位经验 Level**：经验块 Level=blob4 句柄 → 对象图无标量/零值节点命中（phase3，见
   phase3-units.md §10）；节点可能是"晋升树实例"引用载荷，需扩展对象图节点语法。
0b. **FacingDirection 方向名 / AIType 取值表 / OriginCityID 编码**：原值可读，语义未标定。

1. **七项产量每回合值**：Yields/YieldIncomes 等 26 个 `[7][句柄]` 列表指向修正对象 DAG
   （对象图节点形状已部分破解，见 phase2-cities.md §1）；面板值 174.6/9.0 等运行时算出。
   解法 = 反汇编 CityYields 求值函数，或按节点 class hash 聚类拟合算子。
2. **增长阈值公式（U2）**：同上，Threshold/Base/Percent/Discount 句柄 → DAG。
3. **幸福度分档值**：Unhappiness/SuplusHappiness 句柄 → 同一 DAG 体系。
4. **0x402 容器形边界**：Properties/Components/Constructibles 等无计数前缀；
   定界后可解建筑清单与玩家实例块 ID/Civilization 字段。
5. **大裸区容器**：字符串调色板与地图图元区——非 VariantValue 编码，含地形/视野原始数据。
6. ~~外交/宗教块的字段语义标定~~ **Phase4 外交已解**（开放边界/余额/战争矩阵/关系分/修正值，
   见 docs/notes/phase4-diplomacy.md）；剩余：AtWar/HasMet 矩阵 slot 映射定证（行 40-57 条目
   与 WarInitiator=63−行 反转读法二义）、type_a→动作名、外交事件记录全字段、宗教块。
7. **外交事件全字段解码**：事件 = [A][3][-1][1][1][需求hash列表…+尾部]，A=12=开放边界已证；
   需求 hash 与 DB RequirementSet 对齐后可还原每个协议的完整语义。

历史方法备忘：游戏内打开面板截图记录可见数值，与存档二进制做差分对账（E1/E0 单操作差分
是最强工具——20 个差异区间即全部状态变化）。
