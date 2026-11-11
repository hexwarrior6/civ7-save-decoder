# Phase 3 — 单位完整化（字段映射 + 类型反查 + 归属 + 交叉验证）

> 2026-11-12。工具：`tools/units.py`（import 复用 `propertybag.py` 的 CRC32/字典，
> 块语法按 `docs/save-format.md` §6；**不依赖** `blockwalk.py` 的容器解析——其 0x402
> 容器形会把子块吞进 container 节点，Phase1 树里 69 个单位组只有 45 个实例可见）。
> 运行：`python3 -I tools/units.py <body.bin> <out.json>`。
> 验证档：E0（远古 t21，截图锚点）→ E1（移动开拓者）→ E5.1（开拓者就位待建城）
> → E5.2（同格建城"图拉"）；另跑通 E2/E6/E7 同构验证。
> 结果：**4 档 0 解析失败**（E0/E1 69 单位、E5.1/E5.2 89 单位），类型/归属/HP/移动力/朝向/
> has_moved 全部落盘，唯一未解 = 经验块 Level 句柄。

---

## 1. 单位组语法（本轮破解）

每个玩家一段、按 slot 顺序排列（E0：31 个玩家，slot 0..30）：

```
玩家实例块 [K=00000003][-1][1][1][56]                       ← ID 字段 = 归属 slot（见 §4）
  ...（产量/幸福/城市等，Phase2 已解）...
Districts 块 [K=crc"Districts"] → 城区实例 ×N
Units 块 [K=crc"Units"=0xd78ea4b2][1][-1][1][1][25]
  ├ Properties: 0x402 容器形（空）
  └ Units: 0x402 容器形 → 子流 = N × 单位组：
      [组前缀 ~32B：8×u32（词1=序号, 词6=FormationID, 其余 02/02/01/0/0/0）]
      实例块 [K=ffffffff][-1][1][1][47]                      ← 单位本体（§2）
      组件块 a0404aaa(2字段,含 TurnsUntilDigCompletes)
      组件块 8be272e4(1字段)
      组件块 00000002(6字段,form5) / 00000003(81字段,战斗修正表) / e1b1aae9(4字段,Individual/Class/ActionCharges)
      战斗块 [K=0x78de489d][1][-1][1][1][10]                 ← Damage（§3）
      移动块 [K=0xca643c19][1][-1][1][1][6]                  ← MovesRemaining FP8（§3）
      宗教块 [K=0x2eec5d17][1][-1][1][1][6]
      经验块 [K=00000006][-1][1][1][18]                      ← Experience（§3）
      奖励块 1336807f(2字段) / 8c0f3f36(2字段)
      [组尾 4B + FXSBLKED]
  └ （Units 块其余字段）Formations 块 [K=crc"Formations"=0xf032dd18]
      └ Formations: 0x402 容器形 → 每单位 1 条 14 字段命令记录（§5）
```

- E0：69 单位组（31 UnitsBlock；玩家 0-23 有单位，玩家 24-29 为**已死亡城邦**（IsAlive=0）
  与 slot=63 的特殊玩家无单位——与玩家实例 IsAlive 一一吻合）。
- E5.1/E5.2（t22）：89 组（AI 一轮生产 +20）。组内子块计数与实例计数恒等（69/69、89/89）。
- 组前缀 32B 的词 6 = FormationID（E0 开拓者 = 262146 = 0x00040002，与实例字段一致）；
  FormationID = (slot 相关基数+序号)，**不全局唯一**（UB[0] 与 UB[1] 的首单位同为 0x00020000），
  命令记录匹配必须限制在同玩家区间内。

## 2. 实例块 47 字段（K=0xffffffff）

E0 开拓者实例 @0x46e707（字段→偏移→值）。全部字段按 schema 顺序定长消费，到最后一个字段
Components (0x402 容器形) 跳过（见 §6）。

| 字段 | 编码 | 开拓者证据字节 | 语义 |
|---|---|---|---|
| Type | Int @0x46e893 | `28 9d 64 d0` = 0xD0649D28 | 单位类型 CRC32 名称哈希（§7 反查 = UNIT_SETTLER） |
| AIType | Int @0x46e897 | `-1` | 人类=-1（AI 单位为非负 id，待标定） |
| **Location** | 0x400 blob8 @0x46e89b | `2d 00 00 00 06 00 00 00` = (45,6) | 所在格 (x,y)；plot = y×74+x = 489 |
| **FacingDirection** | UInt8 @0x46e8a7 | `03` | 朝向（E1 西移后 3→4；枚举方向名未标定，原值直读） |
| ProcessedTurn | Bool @0x46e8ab | 0 | |
| Domain | Int @0x46e8b4 | 2 | 陆地单位=2；E5 的 4 个 UNIT_GALLEY=0（海军）→ 0=海军/2=陆地（两值实测） |
| Embarked | Bool @0x46e8b8 | 0 | 是否上船 |
| DelayedDeath | Bool @0x46e8ba | 0 | 已死标记（E5.2 被消耗的开拓者 = 仍 0，位置变哨兵值） |
| AbilitiesPossessed / AbilityTotalChargesRemaining / AbilityRechargeTurnsRemaining | 0x400 blob | 空表/`0a000080…` | 能力表（`0a 00 00 80` = Tag 型空表头，未逐项解） |
| BuildCharges | Int @0x46e937 | 0 | 建城次数（开拓者建城后应减，E5.2 未逐单位复核） |
| SightPlots | 0x400 blob @0x46e977 | `[7][0,0][489,1][563,1]…` | 视野 7 格 plot 列表（Phase1 已差分验证） |
| **FormationID** | UInt @0x46e9b7 | 262146 | 单位编队 id；与组前缀词 6、命令记录末字段一致 |
| ArmyID / PackedCommanderArmyID | UInt | 0xffffffff | 未编入军队 |
| OriginCityID | UInt @0x46ea06 | 65536 = 0x00010000 | 产出城（编码未解，疑 [slot][idx]） |
| TimeoutOffMapData | 0x400 blob8 | `f1d8ffff f1d8ffff` = (-10000,-10000) | 离图哨兵坐标（E5.2 被消耗开拓者的 Location 即此哨兵） |
| FortificationTurnModifer / AirInterceptionRange | 0x400 blob4 | 句柄 0x1de47/0x1de3b | 对象图句柄（同一 id 空间 ~122k-139k） |
| Components | 0x402 容器形 @0x46ea47 | `[01][子流]` | 子组件流：紧跟 K=0xa0404aaa 等块（结构见 §6） |

其余字段（BonusPointsPerKill、OperationTimer、FortifyTurns、KillCount、FullMovesWhenCaptured、
GoldSiphoned、CanEarnExperience、CanPackIntoArmy、OpponentID、SightModifiers、Operations 等）
全部原值直读（多为 0/空表），见 JSON。

## 3. 战斗 / 移动 / 经验 子块（HP 与移动力来源）

三个子块结构相同：`[K][1][-1][1][1][count]` + schema + **Properties 容器形** + 剩余字段值
+ FXSBLKED。E0 开拓者证据字节：

| 块 | 偏移 | 字段 | 证据字节 | 值 | 面板锚点 |
|---|---|---|---|---|---|
| 战斗 @0x46f0b8 | Properties 容器 0x46f120→0x46f190 | | `[01][04][00 00 00][4 条目][FXSBLKED]` | | |
| | | **Damage** Int @0x46f190 | `00 00 00 00` | 0 | HP=100−Damage=**100/100 ✓** |
| | | EligibleToHeal Bool @0x46f194 | `01`（E1→`00`） | 1 | Phase1 差分 #13 实为 EligibleToHeal 1→0（原笔记误标为"MovementChanges 队列计数"） |
| | | ExtraEnemyHeal/ExtraNeutralHeal/ExtraFriendlyHeal | 3×blob4 句柄 0x21cbc/0x21cd6/0x21cbd | | 对象图句柄 |
| | | CanHealAfterAction/RespawnHealth/RespawnTimer/IsRespawning | 0 | | |
| 移动 @0x46f1bf | Properties 容器 0x46f207→0x46f41f | | `[01][0c][00 00 00][12 条目][FXSBLKED]` | | |
| | | **MovesRemaining** FP8 @0x46f41f | `00 03 00 00` = 768 | **3.0** | 面板移动力 3/3 ✓ |
| | | MovementChanges 0x400 @0x46f423 | `[04][be 1c 02 00]` = 句柄 138430 | | |
| | | IgnoreObstacleHashes 0x400 | `[04][00000000]` 空 | | |
| | | EmbarkationType Int @0x46f433 | `11 a4 b4 5b` = 0x5BB4A411 | | 值为 CRC 型常量（枚举名未解，E0/E1 恒定） |
| | | EmbarkedMovementModifier Int | 0 | | |
| 经验 @0x46f4db | Properties 容器 0x46f57f→0x46f58f | | | | |
| | | CanPromote Bool @0x46f58f | 0 | | |
| | | **Experience** Int @0x46f590 | 0 | | 新单位 0 经验 ✓ |
| | | Level blob4 @0x46f598 | 句柄 0x21CBF = 138431 | **未解** | 句柄在对象图无标量节点（见 §9） |

**解析方法**（对 4 档全部 69+89+69+69+69 块零失败）：Properties 容器 = `[len=1][条目数 u8]
[pad 3][条目区][FXSBLKED]`，条目 = `[名称hash u32][类型 u32][值按类型定长(≤4B 一律占 4B)]`
（E0 实测：战斗 4 实条目+4 条 `[00000001][Int8][0]` 填充对；移动 12 实条目 + 9 填充对 +
3 个 VariantObject 条目 = 含 16B GUID 样载荷）。跳过容器到 FXSBLKED 后按 schema 严格读剩余
字段，**以块尾 FXSBLKED 校验收尾**，失败则换下一个候选块头。

## 4. 归属（Owner）

实例块 47 字段中**没有** Owner 字段——归属由容器结构给出：

- **归属 = 最近前置玩家实例块的 ID 字段**。玩家实例 [K=00000003][-1][1][1][56]，值区为
  Properties 容器 + `ID:Int, IsAlive:Bool, WasEverAlive:Bool, IsTurnActive:Bool, Civilization:Int`。
- E0 实测 31 个玩家实例 ID = 0..30（最后一个 = 63），文件顺序 = ID 顺序 ✓；每玩家的
  UnitsBlock 紧随其后（UB 序 = slot 序，双锚点互证）。
- slot 0 = 俄罗斯（人类）：E0 的开拓者 (45,6) + 2 侦察兵归 slot 0 ✓（与 phase2 城市归属
  St. Petersburg slot0 同坐标互证；与 E5.2 图拉 owner_slot=0 互证）。
- 玩家 24-29 IsAlive=0（6 个已死亡城邦）→ 无单位 ✓；玩家 63（IsAlive=0，ID=63）无单位。
- Civilization 字段值 = 对象句柄（0x0b0dacea 等，非 CRC；6 大文明各不相同，18 个活城邦共享
  0x40d617db，6 个死城邦共享 0x335783e1——疑"模板对象"句柄，语义未解）。

## 5. 命令/Formations 记录（14 字段）——HasMoved 来源

Units 块的 Formations 容器内，**每单位 1 条**记录（E0 69 条 = 69 单位；E5 同 89=89）：

```
[K=ffffffff][-1][1][1][14]：Location:400, MovesRemaining:407, Domain:8, EmbarkType:8,
  IsEmbarked:1, CanAttack:1, ?Bool, ?Bool, HasMoved:1, ?Bool, ?Bool, LastPath:400, ?:400, ?:400
```

- E0 开拓者记录 @0x46ff84：Location @0x47000c = (45,6)、MovesRemaining @0x470014 = 3.0、
  **HasMoved @0x470024 = 0**（E1 = 1）——与 Phase1 差分 #15/#16 逐字节吻合。
- 末字段 = blob8 `[u32 数量][u32 FormationID]`（开拓者 = `[01][0x00040002]`）→
  **同玩家区间内按 FormationID 精确匹配单位**；匹配失败再按 Location 兜底，再失败如实输出
  has_moved=null（E5.2 仅被消耗的开拓者 1 条未匹配——其记录随单位消失已失效）。
- **打包单位无独立记录**（现代档实测）：被指挥官打包的单位 Location=(-10000,-10000)、
  FormationID=0xffffffff，记录数 = 单位数 − 打包数（现代档 204 单位 189 条记录，16 条
  has_moved=null 全为打包单位）；其移动状态挂在指挥官的记录上，未进一步展开。
- **HasMoved 语义 = 本回合是否已消耗移动力**：E0（t21 回合开始）64/69 True = AI 已行动，
  False 的 5 条 = 人类 3 单位 + 诺曼/法兰西刚出厂未动的战士 ✓；E5.1（人类回合中）开拓者
  True、侦察兵 False、5 条刚出厂单位 False ✓。
- 记录与移动块的 MovesRemaining 镜像：E0/E1 69/69、E5.1 88/89、E5.2 87/89 一致；不一致的
  1 条 = 诺曼刚出厂的开拓者（块值 0.0，记录 2.0）——刚生产单位的记录滞后，读取以移动块为准。
- 记录尾部可有未入 schema 的附加字节（E0 开拓者记录后 36B：`00000400 5 3 7 3 4 5 6 7`，
  与组尾的 36B 同构），语义未解；解析器读满 14 字段即止、不强求终止符。

## 6. 0x402 容器形的两种子形（本轮补充观察）

| 子形 | 例子 | 结构 |
|---|---|---|
| 属性表形（小） | 战斗/移动/经验块的 Properties | `[len=1][条目数 u8][pad3][条目×N][FXSBLKED]`，条目=`[hash][type][值4B对齐]` |
| 收集容器形（大） | 实例 Components / Units / Formations | `[头部若干 u32][子块流]`；实例 Components 实测 `[len=1]` 后**无载荷字节**直接跟 K=0xa0404aaa 块头；Units/Formations 实测头 = `0x00010002,0,16,8,3,…` + 骨架值（语义未解）。子块自带 FXSBLKED，容器终点=最后一个子块的终止符 |

通用跳过法（units.py 采用）：从 `[len]` 后搜索第一个 FXSBLKED 作容器终点——对本轮全部
块收敛（所有子块/值校验通过）；头部语义精确解留待后续。

## 7. 单位类型反查（Type CRC32 → 名称）

- Type = CRC32(名称哈希)（同 §6.1 参数）。**方法**：在 body 全文 grep `UNIT_[A-Z0-9_]+`
  （DB 定义区快照，E0 得 58 个、E5 档 132 个），逐一 CRC 建 reverse 字典；再对 `UNIT_X_NAME`
  剥掉 `_NAME` 生成推断名（loc key 惯例）；仍缺的（存档 DB 快照不含定义的单位）从**游戏本体
  data XML/sql**（`CivilizationVII.app/Contents/Resources/{Base,DLC}`）grep `UNIT_*` 补充
  ——units.py 内建此后备，游戏不在标准路径时自动跳过。
- 命中即确定（CRC 无碰撞风险）；`type_source` 字段区分 `db-direct`（存档内定义名）/
  `loc-inferred`（_NAME 剥离）/ 游戏数据补查。

| Type 哈希 | 名称 | 来源 | E0 | E5.1/E5.2 | 备注 |
|---|---|---|---|---|---|
| 0xD0649D28 | UNIT_SETTLER | db-direct | 1 | 3 | 开拓者（Phase1 已验证） |
| 0x6F961899 | UNIT_SCOUT | db-direct | 29 | 29 | 侦察兵（基移动力 2.0 ✓） |
| 0xE9B57B30 | UNIT_WARRIOR | db-direct | 38 | 44 | 战士 |
| 0x9023E7E3 | UNIT_MIGRANT | db-direct | 1 | 1 | 移民（波斯首都 (62,14) 1 个） |
| 0x2B175344 | UNIT_GALLEY | db-direct | 0 | 4 | 划桨船（海军，E5 新出现） |
| 0x5CEAC7C9 | UNIT_SLINGER | 游戏本体 data XML | 0 | 8 | 投石手：8 个活城邦各 1（存档 DB 快照不含此定义名，故必须靠游戏文件或人工字典） |

新增 27 个 `UNIT_*` 类型名已按字母序插入 `tools/fieldnames.txt`（UN 大写段，1180→1207 行）。

## 8. E0 全单位清单（69 单位，人类 slot0 加粗场景见 §9）

| # | 块偏移 | 类型 | slot | 位置(x,y) | HP | 朝向 | 移动力 | 经验 | 已移动 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0x46c637 | UNIT_SCOUT | 0 | (28,5) | 65 | 2 | 2.0 | 0 | 否 |
| 1 | 0x46d685 | UNIT_SCOUT | 0 | (47,9) | 100 | 5 | 2.0 | 0 | 否 |
| 2 | **0x46e707** | **UNIT_SETTLER** | **0** | **(45,6)** | **100** | **3** | **3.0** | 0 | 否 |
| 3 | 0x4c5c1f | UNIT_SCOUT | 1 | (70,17) | 100 | 0 | 0.0 | 0 | 是 |
| 4 | 0x4c6cd6 | UNIT_SCOUT | 1 | (61,7) | 100 | 2 | 0.0 | 0 | 是 |
| 5 | 0x4c7d3c | UNIT_MIGRANT | 1 | (62,14) | 100 | 3 | 2.0 | 0 | 是 |
| 6 | 0x54cd51 | UNIT_SCOUT | 2 | (18,31) | 70 | 0 | 1.0 | 0 | 是 |
| 7 | 0x54de27 | UNIT_SCOUT | 2 | (25,17) | 100 | 2 | 0.0 | 0 | 是 |
| 8 | 0x5b3849 | UNIT_SCOUT | 3 | (46,38) | 100 | 0 | 0.0 | 0 | 是 |
| 9 | 0x5b48f8 | UNIT_SCOUT | 3 | (53,23) | 100 | 2 | 0.0 | 0 | 是 |
| 10 | 0x61060d | UNIT_SCOUT | 4 | (16,26) | 55 | 3 | 1.0 | 0 | 是 |
| 11 | 0x61166b | UNIT_SCOUT | 4 | (40,6) | 100 | 2 | 0.0 | 0 | 是 |
| 12 | 0x6126a9 | UNIT_WARRIOR | 4 | (27,19) | 100 | 3 | 2.0 | 0 | 否 |
| 13 | 0x66de60 | UNIT_SCOUT | 5 | (69,15) | 100 | 0 | 0.0 | 0 | 是 |
| 14 | 0x66eecf | UNIT_WARRIOR | 5 | (65,25) | 100 | 3 | 2.0 | 0 | 否 |
| 15-17 | 0x6c8075/0x6c9133/0x6ca1aa | WARRIOR/SCOUT/WARRIOR | 6 | (19,33)/(10,28)/(19,32) | 100 | 3/1/3 | 0.0 | 0 | 是 |
| 18-20 | 0x6d9c6d/0x6dad33/0x6dbd8a | WARRIOR/SCOUT/WARRIOR | 7 | (61,38)/(68,33)/(62,36) | 100 | 3/2/2 | 0.0 | 0 | 是 |
| 21-23 | 0x6eb4cf/0x6ec59d/0x6ed604 | WARRIOR/SCOUT/WARRIOR | 8 | (41,23)/(44,23)/(39,24) | 100 | 3/3/2 | 0.0 | 0 | 是 |
| 24-26 | 0x6fcb4e/0x6fdc1c/0x6fec8b | WARRIOR/SCOUT/WARRIOR | 9 | (37,9)/(36,8)/(37,8) | 100 | 3/4/4 | 0.0 | 0 | 是 |
| 27-29 | 0x70e611/0x70f6e7/0x71071d | WARRIOR/SCOUT/WARRIOR | 10 | (39,34)/(43,41)/(40,36) | 100/54/100 | 3/3/3 | 0.0 | 0 | 是 |
| 30-32 | 0x71fe2a/0x720f00/0x721f6f | WARRIOR/SCOUT/WARRIOR | 11 | (45,33)/(58,22)/(46,33) | 100 | 3/4/2 | 0.0 | 0 | 是 |
| 33-35 | 0x731878/0x732936/0x73399d | WARRIOR/SCOUT/WARRIOR | 12 | (3,38)/(9,36)/(4,38) | 100 | 3/3/5 | 0.0 | 0 | 是 |
| 36-38 | 0x742eed/0x743fbb/0x74503a | WARRIOR/SCOUT/WARRIOR | 13 | (51,24)/(56,30)/(52,24) | 100 | 3/1/3 | 0.0 | 0 | 是 |
| 39-41 | 0x754997/0x755a55/0x756a83 | WARRIOR/SCOUT/WARRIOR | 14 | (10,25)/(23,31)/(8,26) | 100 | 3/1/5 | 0.0 | 0 | 是 |
| 42-44 | 0x766519/0x7675c7/0x768646 | WARRIOR/SCOUT/WARRIOR | 15 | (14,10)/(16,9)/(13,9) | 100 | 3/4/4 | 0.0 | 0 | 是 |
| 45-47 | 0x777bb9/0x778c77/0x779cc5 | WARRIOR/SCOUT/WARRIOR | 16 | (56,17)/(64,11)/(56,22) | 100 | 3/3/0 | 0.0 | 0 | 是 |
| 48-50 | 0x7894d0/0x78a596/0x78b5e4 | WARRIOR/SCOUT/WARRIOR | 17 | (21,6)/(11,9)/(19,8) | 100 | 3/2/5 | 0.0 | 0 | 是 |
| 51-53 | 0x79acdb/0x79bdb1/0x79cdff | WARRIOR/SCOUT/WARRIOR | 18 | (32,5)/(28,15)/(30,6) | 100 | 3/3/3 | 0.0 | 0 | 是 |
| 54-56 | 0x7aca79/0x7adb37/0x7aeb75 | WARRIOR/SCOUT/WARRIOR | 19 | (53,7)/(52,13)/(54,7) | 100 | 3/0/0 | 0.0 | 0 | 是 |
| 57-59 | 0x7be0af/0x7bf155/0x7c01a3 | WARRIOR/SCOUT/WARRIOR | 20 | (28,26)/(29,14)/(29,23) | 100 | 3/1/1 | 0.0 | 0 | 是 |
| 60-62 | 0x7cfc60/0x7d0d26/0x7d1dad | WARRIOR/SCOUT/WARRIOR | 21 | (69,33)/(49,31)/(67,31) | 100 | 3/3/2 | 0.0 | 0 | 是 |
| 63-65 | 0x7e171e/0x7e27ec/0x7e3822 | WARRIOR/SCOUT/WARRIOR | 22 | (33,14)/(42,6)/(34,11) | 100 | 3/4/4 | 0.0 | 0 | 是 |
| 66-68 | 0x7f3353/0x7f4409/0x7f5488 | WARRIOR/SCOUT/WARRIOR | 23 | (58,26)/(53,29)/(59,28) | 100 | 3/2/2 | 0.0 | 0 | 是 |

结构摘要：6 主文明 + 18 活城邦有单位（69）；4 个受伤单位全是侦察兵（slot0/2/4/10，
HP 65/70/55/54，远程骚扰所致，E0 无正面战争）；人类 slot0=2 侦察+1 开拓者，**无战士**
（阿拔斯/罗马同样无地面战斗单位，仅侦察兵——早期侦察换家了，怪但如实记录）；
slot 24-30（6 死城邦+ID63）无单位。

## 9. 交叉验证

### 9.1 E0 → E1（开拓者移动 2 格，Phase1 差分复验）

| 锚点 | E0 读数 | E1 读数 | 面板/Phase1 | 结论 |
|---|---|---|---|---|
| 开拓者 Location | (45,6) plot 489 | (43,6) plot 487 | (45,6)→(43,6) | ✓ |
| 开拓者 HP (Damage) | 0 → 100 | 0 → 100 | HP 100/100 保持 | ✓ |
| 开拓者 MovesRemaining | 3.0 | 1.0 | 3/3 → 1/3 | ✓ |
| 开拓者 FacingDirection | 3 | 4 | 3→4 | ✓ |
| 开拓者 has_moved（命令记录 @0x470024） | false | true | Phase1 差分 #16 | ✓ |
| 记录镜像 MovesRemaining | 3.0 | 1.0 | 与移动块一致 | ✓ |
| 其余 68 单位 | — | 全字段无变化 | 单操作差分 | ✓ |

### 9.2 E5.1 → E5.2（开拓者建城"图拉"，关键交叉验证）

| 锚点 | 读数 | 结论 |
|---|---|---|
| E5.1 俄罗斯（slot0）开拓者位置 | (42,9) plot 708，has_moved=true，移动力 2.0 | "已在目标格就位待建城" ✓ |
| E5.2 新增城市 | LOC_CITY_NAME_RUSSIA7 @ **(42,9) plot 708**，owner_slot=0，建城回合 22 | **城市坐标 == E5.1 开拓者坐标** ✓ |
| 城名 l10n | `LOC_CITY_NAME_RUSSIA7` = **图拉**（游戏 zh_Hans_CN_Text.xml） | 与任务锚点"图拉" ✓ |
| E5.2 该开拓者 | Location = (-10000,-10000)（离图哨兵值，同 TimeoutOffMapData 哨兵） | 建城后被消耗 ✓ |
| 其余 88 单位 | E5.1→E5.2 全字段零变化 | ✓ |
| 命令记录匹配 | E5.2 仅此消耗单位 has_moved=null（记录失效），88/89 匹配 | ✓ |

### 9.3 E0 → E5.1（间隔一个 AI 回合，健全性）

+20 单位全部归属 AI 文明/城邦（8 SLINGER=8 城邦、4 GALLEY、2 SETTLER、6 WARRIOR），
人类 slot0 无新增；48 单位位置变化（AI 行动）；4 侦察兵受伤；无单位消失——与"回合 21→22
完整 AI 轮"自洽。E2/E6/E7（同 t21 实验档）均 69 单位 0 未解，工具回归通过。

### 9.4 现代档回归（AutoSave_02_0004，t4）

204 单位 / 19 玩家 / 189 命令记录；类型 0 未解（CUIRASSIER 56、LINE_INFANTRY 29、FRIGATE 18、
FIELD_CANNON 17、ARMY_COMMANDER 12、SETTLER 12 等，全部经游戏本体 XML 后备字典反查）；
归属/HP/移动力/朝向 0 未解；16 条 has_moved=null = 指挥官打包单位（见 §5）。

## 10. 未解项（如实）

1. **经验块 Level 句柄**（blob4 ~138k）：对象图区间无标量节点/零值节点命中（phase2 节点形状
   反查失败）——等级暂输出 `level=null, level_handle=<id>`。Experience 本身是直读 Int（新单位 0）。
   下一步：该 id 指向的对象可能是"晋升树实例"而非数值；需扩展对象图节点形状（引用载荷）。
2. **FacingDirection 枚举名**：1-5(0) 有值，3→4 对应西移；方向名（北/东北/…）未标定，原值直读。
3. **EmbarkationType 枚举名**：恒为 CRC 型常量 0x5BB4A411（枚举名未解）；Domain 两值已实测
   （0=海军 GALLEY、2=陆地），其余取值未遇。
4. **收集容器形头部**（Units/Formations/Components 的 `0x00010002,0,16,8,3,…` 骨架与
   `[01][count][pad]` 属性表形的关系）：语义未解；本轮用"FXSBLKED 扫描 + 严格值校验"绕过，
   4 档零失败。
5. **命令记录尾部附加字节**（36B `00000400 5 3 7 3 4 5 6 7` 等）与 14 字段之外的 3 个 0x400
   字段的值语义（LastPath 空、id 对、哨兵对）部分未解——HasMoved/Location/MovesRemaining
   三个目标字段已验。
6. **AIType 取值表**（人类=-1，AI 单位 observed 0..?）与 OriginCityID 编码（0x00010000 疑
   [slot][idx]）未标定。
7. **Type 反查覆盖面**：反查字典来自存档 DB 快照 + 游戏本体 XML；若单位类型两者都没收录
   （如某些 DLC/ modded 名），输出 type_hash 原值 + type=null，不猜名。

## 11. 工具用法

```bash
python3 -I tools/units.py <body.bin> <out.json>
# 输出: {"num_units","num_players","players":[{slot,alive,...}],
#        "units":[{type,type_hash,type_source,owner_slot,location,plot,hp,damage,
#                  moves_remaining,facing,has_moved,experience,level,level_handle,
#                  formation_id,domain,embarked,build_charges,...,combat|move|exp|record_offset}],
#        "unresolved":{...计数}}
```
