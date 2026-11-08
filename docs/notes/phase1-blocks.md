# Phase 1 — FXS 属性包通用块遍历（块目录）

> 2026-11-09。工具：`tools/blockwalk.py`（import 复用 `propertybag.py` 的 CRC32/类型表/字典）。
> 运行：`python3 tools/blockwalk.py <body.bin> <out.json>`。
> E0 实测：9,573,774 B body，属性包起点 = 第一个 `FXSBLKED` @0x2e35f8。
> 结果：**376 块完整解析**、113 块在容器形 0x402 处截断（见 phase1-unknowns.md U3b）、
> 273 个裸区（其中 33 个 >4KB 的大区 = 字符串调色板/地图图元等非 VariantValue 容器）。

## 1. 块语法（本轮最终确认）

```
块实例 = [u32 A]            ← 成员键 hash / 对象实例 id（二义，见 §2）
         [u32 1]?           ← 仅 6-u32 形式有（立即成员标志）
         [-1] [1] [1] [u32 count]
         [count × (u32 hash, u32 type)]     ← schema：type 低16位=VariantValueType，高16位=modifier
         [values 按条目序]
         [8B "FXSBLKED"]?   ← 376 个完整块中 339 个以终止符结尾
```

值编码（WriteSchema/VariantValue::Serialize 反汇编 + E0 字节双重验证）：

| 类型 | 磁盘编码 | 例子（E0 实测） |
|---|---|---|
| 0x402 字符串 | `[u32 len][len 字节][pad 到 4 对齐][8B FXSBLKED]` | Properties=`[01][00 00 00 00][FXSBLKED]`（空串） |
| 0x400/0x403 尺寸块 | `[u32 size][size 字节]` | CurrentFood=`[04][00 00 28 00]`=10240 |
| 0x407 FixedPoint8 | `u32 raw`，值=raw/256 | GoldBalance=7680 → 30.0 ✓面板 |
| 0x008 Int / 0x009 UInt | 4 字节 | CurrentTurn=21 |
| 0x001 Bool | **1 字节** | DelayedDeath=0 |
| 字符串列表 | `[u32 count][count × (u32 len, bytes)]` 无终止符 | 城市名池 [46][21]["LOC_..."]×46 |

字符串列表无对齐无终止符（LOC_CITY_NAME_GREECE1 序列逐字节验证）；单个字符串有 pad+终止符。

## 2. 头部二义性（如实记录）

`[-1][1][1][count]` 前可出现 0/1/2 个上下文 u32（walk 顺序解析不回扫，全部保留）：

| 实例（E0 偏移） | 前置 u32 | 解释 |
|---|---|---|
| 0x2e3600 游戏根 | `1` | 无成员键，`1`=流版本（WriteComponents 首写 u32 1） |
| 0x467fcd 城市实例 | `0, 0x0b0dacea` | `0x0b0dacea`=城市实例 id |
| 0x464ca5 玩家金库 | `0xd34dab99, 2` | 0xd34dab99=成员键，2=schema 注册序号 |
| 0xa787bc(modern) 增长块 | `0x635c5324, 1` | 0x635c5324=Growth 键，1=序号 |

`Serialization::DelineatedData::WriteSchema` 反汇编确认固定写 `[-1][1][id][count]`
（id 为每流计数器，捕获流各自从 1 起）；`BeginWrite`/`Immediate` 决定前置 u32 的有无。

## 3. 块目录（E0，按 schema 特征去重后 69 种；列出关键类型）

| 块（键→名） | count | 字段 schema（前几项） | 出现次数 | 典型样例偏移 | 解读 |
|---|---|---|---|---|---|
| 0x00000001→(root) | 13 | Rules:402, GameProcessor:402, CurrentTurn:8, Difficulty:402, MaxTurns:8, GamePaused:1, Map/PlayerManager/SyncRandom:402, MapSyncRandom:400, Components/GameEffects/GlobalAi:402 | 1 | 0x2e3600 | 游戏根对象 |
| 0x00000003→hash_00000003 | 56 | Properties:402, ID:8, IsAlive:1, WasEverAlive:1, IsTurnActive:1, Civilization:8… | 9 | 0x462b3a | 玩家实例（每文明一个） |
| 0x00000002→hash_00000002 | 19 | Properties:402, **GoldBalance:407**, CanPurchaseWonders:400, TotalMaintenance:400, UnitMaintenance:400…GoldEarned/GoldSpent/GoldDeducted:407 | 10 | 0x464ca5 | 玩家金库/财政。E0 GoldBalance=7680=**30.0 金 ✓顶栏** |
| 0x635c5324→hash(现代档) | 17 | CurrentFood:400, CurrentStarvation:400, GrowthType:400, MigrationCityID:400, ProjectType:400, TurnLastNotifyStarving:8…NextGrowthFoodThreshold:400 | 每城 1 | E0 第一个 0x468c49 | 城市增长（17 字段全对位） |
| 0x0b0dacea→(城市实例 id) | 29 | Location:400, AiId:9, DelayedDeath:1, HasBuildQueue:400…Population:400, RuralPopulation/UrbanPopulation/WorkerPopulation:400, Components:402 | 每城 1 | 0x467fcd | 城市属性图 |
| 0xffffffff→hash_ffffffff | 47 | Type:8, AIType:8, **Location:400**, FacingDirection:8, ProcessedTurn:1…SightPlots:400, FormationID:8…Components:402 | 每单位 1 | 0x46e707（开拓者） | 单位实例 |
| 0xffffffff→hash_ffffffff | 14 | **Location:400, MovesRemaining:407**, Domain:8, EmbarkType:8, IsEmbarked:1, CanAttack:1…HasMoved:1, LastPath:400 | 8 | 0x46ff88 | 单位命令缓存（AI 视图镜像） |
| 0x00000001→hash_00000001 | 10 | Properties:402, **Damage:8**, EligibleToHeal:1, ExtraEnemyHeal:400…RespawnHealth… | 11 | 0x46e0d2 | 单位战斗/生命（Damage=0 ⇒ HP 100/100 ✓） |
| 0x00000001→hash_00000001 | 6 | Properties:402, **MovesRemaining:407**, MovementChanges:400, IgnoreObstacleHashes:400, EmbarkationType:8, EmbarkedMovementModifier:8 | 13 | 0x46e1dd | 单位移动力。E0 MovesRemaining raw=768=**3.0 ✓面板 3/3** |
| 0x00000006→hash_00000006 | 18 | Properties:402, CanPromote:1, Experience:8…Level:400… | 2 | 0x46e4f5 | 单位经验/晋升 |
| 0x00000005→hash_00000005 | 78 | Properties:402, Tokens:400, AvailableTokens:400… | 12 | 0x4bf3d9 | 外交影响力令牌 |
| 0x00000002→hash_00000002 | 33 | Properties:402, Trees:400, UnlockedTraditions:400, MainTree:8, ActiveTree:8 | 12 | 0x4bee86 | 文化树/传统 |
| 0xd60fd288→hash_d60fd288 | 8 | Properties:402, Tree:8, LastCompletedNode:8, MasteryCost:400, ScienceOverflow:407… | 10 | 0x7b98a7 | 科技树进度 |
| 0x210e4ba2→Cities | 17 | Properties:402, Cities:402, NumCities:400, NumTowns:400, SettlementCap:400… | 12 | 0x4c153f | 玩家城市汇总 |
| 0x16dc6950→hash_16dc6950 | 43 | Properties:402, YieldPerConvertedCity:400… | 12 | 0x4c0ffe | 宗教/转化产出 |
| 0x3a9f4f31→hash_3a9f4f31 | 13 | Properties:402, FixedPointArrays:400, DiplomaticModifiers:400… | 12 | 0x4c0926 | 外交关系（含修正值数组） |
| 0x479b2070→hash_479b2070 | 7 | Properties:402, NotificationLevel:400, Occurrences:400… | 13 | 0x47638a | 通知 |
| 0x6979b751→hash_6979b751 | 75 | Properties:402, MaxMeleeStrengthTrained:8… | 10 | 0x7b85c5 | 军事统计 |
| 0x00000003→hash_00000003 | 81 | FriendlyTerritoryCombatMod:8, PlunderYieldModifier:8…（无 Properties 头） | 8 | 0x46db71 | 战斗修正表 |
| 0x00000002→hash_00000002 | 11 | CityId:400, Location:400, Region:9, Capital:1, TurnsSinceObserved:8, Population:8 | 8 | 0x7c76d8 | 已探明城市情报 |
| 0x926896f2→Resources | 16 | Properties:402, AvailableResourceCounts:400… | 10 | 0x7b81d1 | 资源库存 |
| 0x00000002→hash_00000002 | 15 | Properties:402, EnabledLegacyPaths:400, SettlementCountScoringItems:400… | 15 | 0x47653a | 遗产路径计分 |

（完整 69 签名清单可由 `blockwalk.py` 输出 JSON 的 stats/节点重建。）

## 4. 已验证的锚点数值（E0 = 截图真值）

| 字段 | 存档字节 | 解析值 | 面板真值 | 结论 |
|---|---|---|---|---|
| CurrentTurn (root) | 0x2e3694 `15 00 00 00` | 21 | 回合21 | ✓ |
| GoldBalance (金库块) | `00 1e 00 00`=7680 | 30.0 | 金30 | ✓ |
| CurrentFood (增长块#0) | `00 00 28 00`=10240 | 40.0 | 增长食物 40/149 | ✓ |
| MovesRemaining (开拓者) | `00 03 00 00`=768 | 3.0 | 移动力 3/3 | ✓ |
| Damage (开拓者) | 无差异 | 0 | HP 100/100 | ✓ |
| Location (开拓者) | blob8=(45,6) | plot 489 | 圣彼得堡旁 | ✓（E1 变 (43,6)） |
| 人口 (城市块 HighestPopulation) | `[4][6]` | 6 | 人口6（现代档雅典 [4][38]=38 ✓） | ✓ |

## 5. 遍历器覆盖/未覆盖

- 覆盖：块（schema+值）、字符串（含终止符校验）、尺寸块、FP8、标量、裸 u32、FXSBLKED 终止符。
- 未覆盖（进 unknowns 清单，0x2e35f8 起共 1,674,924 B = 17.5%）：
  1. 0x402 **容器形**（Properties/Components/Controllers/Armies/Units 等，112 处）：
     `[len=1]["\x00"]` 后**无终止符**，直接跟子块流（每子块自带 FXSBLKED）。
  2. 游戏根的 GameProcessor/Map/PlayerManager/SyncRandom 大负载（0x2e368c–0x2e3d3b）。
  3. 字符串调色板区（"UIDL"/"ave"/"Turn"… 前缀共享压缩表，0x8065dd 等 7 段 ×41KB）。
  4. 地图图元区（0x4d6dd0 起 375KB：[hash][1][1][0xa00048]… 单元图，非 VariantValue）。

## 6. 验收修复（2026-11-09 第二轮）：容器形 0x402 与字节对齐

原版 walker 两处缺陷：① 重同步/裸区按 4 字节步进，而流并非 4 对齐（玩家块起于 ≡2 mod 4，
≡3 处的 FXSBLKED 被跳过 ⇒ 俄罗斯金库整段被跳过）；② 容器形 0x402（Properties/Units/Components）
直接判 partial 丢字段，且容器内的假块头（数据区 [-1][1][1][大数]）会吞掉 2.6MB。

修复（tools/blockwalk.py）：① 全程字节级锚点搜索（FXSBLKED 或 [-1][1][1]，块锚回退 [K]）；
② 容器形 0x402 → `{"kind":"container","children":[...]}`：从 [len] 后按块语法连续解析子块，
终止条件 = 严格对位（下一 schema 字段为自校验类型：带终止符字符串/固定尺寸 blob）/ 异构子块
（schema 特征 (count, 前4条目hash) 与首个干净子块不同）/ 子块损坏 / 裸区>256B / 跨度上限；
块头加两道验证（count≤0xFFFF + 前4条目类型字低16位≤0x407）；③ partial 块保留全部已解字段，
失败字段记 `('unreadable', offset)`，不丢数据。

验证（E0 重生成 /tmp/scratch/E0_walk.json）：**金库块 31/31 全部 19/19 字段进树**，
俄罗斯 @0x464ca5 GoldBalance=**30.0**，六主流文明 = **30/181/25/28/205/40**，
其余 25 个（城邦等）= 0.0；块 ok 由 376 → **1806**（含容器子块），E0/E1 一致；
回归锚点全部保持：CurrentFood=40.0、E1 树内直接可见开拓者 Location (45,6)→(43,6)、
MovesRemaining 3.0→1.0。容器仍会截断（Properties/Components 201+91 处，截断点如实标注），
但子块与已解字段全部在树中；边界精确定界留待下一阶段。
