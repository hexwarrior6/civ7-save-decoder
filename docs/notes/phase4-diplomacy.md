# Phase 4 — 外交关系（开放边界定位 + 全文明关系表）

> 2026-11-12。工具：`tools/diplomacy.py`（import 复用 `propertybag.py` 的 CRC32/字典，
> 块定位按 units.py 的"块头签名 + 首条目 hash + 值区严格解析"全文搜索）。
> 运行：`python3 -I tools/diplomacy.py <body.bin> <out.json>`。
> 验证档：E0（远古 t21 基线）vs E2（同 t21 实验档，唯一操作 = 与诺曼查理曼开放边界；
> 退档重存漂移大，差分只看方向与量级）+ MODERN（AutoSave_02_0004 现代档，回归验证）。
> 结果：**开放边界状态位、影响力余额、战争/和平矩阵、同盟/友谊矩阵、关系分、外交修正
> 数组全部定位**；每对文明关系表已产出（e0_diplomacy.json / e2_diplomacy.json）。

---

## 1. 本轮结论：开放边界的存盘位置与编码

**位置**：每玩家一个的"外交/影响力块"（K=`0x00000005`，78 字段，31 个实例 = slot 0..29 + 63），
字段 **`HasOpenBordersFrom` = blob 64 字节 = 64×u8**（无 count 前缀），数组下标 = 对方玩家 slot，
值 1 = 开放、0 = 未开放（其余 63 字节全 0 为常态）。

**语义（位方向）**：P 的块里 `HasOpenBordersFrom[X]=1` ⇔ **P 可以进入 X 的边界**（X 对 P 开放；
字段名直译"从 X 处拥有开放边界"）。三条独立证据：

1. **E2/E0 差分**：31 个块逐字段 raw diff，唯一变化 = slot0（俄罗斯 = 人类 = 行动发起方/付款方）
   的 bit[4]=1（诺曼查理曼）。若按 u32 数组解读会落在下标 1（波斯）——与实际操作对象
   （诺曼 = slot4）矛盾，故元素 = u8 确证。
2. **现代档宗主锚点**：cs6 的宗主 = slot3（cs6 的 tribe 块 `Suzerain=3`），开放边界位 =
   slot3.bit[6]=1 而 cs6.bit[3]=0 → **宗主获得进入城邦的边界（单向）**；cs11（宗主=2）同理。
   若位方向相反（"我开放给 X"）则宗主位应出现在城邦块上——实测相反。
3. **游戏本体 l10n**（`base-standard/l10n/zh_Hans_CN_Text.xml`）：
   `LOC_DIPLOMACY_PROJECT_OPEN_BORDERS_INITIAL` = "对方玩家的边界将对你开放。"（发起方受益）。

**开放边界相关字段组**（同块内）：

| 字段 | 编码 | E0 | E2 | 说明 |
|---|---|---|---|---|
| HasOpenBordersFrom | 64×u8 | 全 0 | slot0: bit[4]=1（唯一变化） | 开放边界状态位 |
| OpenBordersEndedTurn | 64×u32 | 全 -1 | 全 -1（未变） | 协议结束回合，结束时才写 |

**E2 佐证链**（开放边界动作 = 以下四处同时变化）：

| 观测 | E0 | E2 | 解释 |
|---|---|---|---|
| slot0 HasOpenBordersFrom[4] | 0 | 1 | 开放边界生效 |
| slot0 DiplomacyBalance | 80.0 | 55.0 | −25 = 外交面板"开放边界"标价 25 ✓ |
| TotalDiplomacyEvents（全局块） | 12 | 13 | +1 事件 |
| ActiveDiplomacyEventsV2 | 5 条 (A=6,7,8,9,11) | 6 条 (+A=12, 615B，旧 5 条逐字节不变) | 新增协议事件 |
| body 内字符串 | 无 | 新增 `PLAYER_DIPLOMACY_OPEN_BORDERS_ACTIVE` / `PLAYER_DIPLOMACY_OPEN_BORDERS_TARGET_PLAYER_ACCEPT` / `LOC_…ACCEPT` | 游戏本体 XML 中 = `DIPLOMACY_OPEN_BORDERS_ACTIVE` stage 的 ModifierId 与其需求/本地化键 |

注：E2 截图顶栏显示"🌐 80 (+10)"，与 E2 存档余额 55 不一致——两种解释：
(a) 截图摄于签署前（面板中"开放边界 25"仍以可执行状态显示）；(b) 顶栏数字含 escrow
（55+25=80，协议期间的承诺令牌）。存档字节以 55 为准，E0 锚点 80 ✓。

---

## 2. 影响力令牌（顶栏锚点已验证）

**余额落盘位置**：每玩家一个的块 K=`0x7d74610f`（15 字段，31 实例），字段
**`DiplomacyBalance` = FP8 直读**（无句柄）。

| slot | E0 | E2 | 说明 |
|---|---|---|---|
| 0 俄罗斯(人类) | **80.0** | **55.0** | 顶栏锚点 80 ✓；E2 = 80−25（开放边界标价）✓ |
| 1 波斯 | 130.0 | 130.0 | AI 累积 |
| 2 阿拔斯 | 129.0 | 129.0 | |
| 3 罗马 | 20.0 | 20.0 | |
| 4 诺曼(查理曼) | 130.0 | 130.0 | |
| 5 法兰西帝国 | 0.0 | 0.0 | |
| 6-23 城邦 | 0.0 | 0.0 | 城邦不累积 |
| 24-29 已死城邦 | 0.0 | 0.0 | |
| 63 | 0.0 | 0.0 | |
| MODERN 0-4 | 748.07 / 336.75 / 264.0 / 321.86 / 176.0 | — | 现代档回归 ✓ |

- **+10/回合** 收入：无落盘原值——来自 `BonusTokensInitiator/Target`、
  `ActionProgressEnvoyModifier` 等 blob 中的修正对象句柄（运行时计算），未解（同产量 DAG）。
- 78 字段块中的 `Tokens / AvailableTokens / ReservedTokens / CommittedTokens /
  ExhaustedTokens / EscrowTokens / NumProjects / NumEndeavors / NumSanctions /
  NumEspionage / NumTreaties / NumAlliances` 全部 = blob4 **对象句柄**（slot0 = 2899-2904
  连号小 id），非数值。对象图反查：Tokens(2904) = 引用聚合节点 → [2903,2901,2900,2899,2902]，
  2903 → 引用 [122161,122162]，2900 → [122163]；节点形状
  `[tag u8][id u32][hashA u32][t2 u8][hashB u32]?[count u8][00][ref×n][id-again u32]`
  （tag 0x81 = 无引用零节点）。122161/122162 的 t2=00 载荷（0x00010000 / 0xffffff00）
  不是 20480(=80×256)，**令牌数值无 FP8 标量落盘** → 未直读（见 §7 未解）。

---

## 3. 全文明关系表（E0 与 E2）

数据源：全局战争/外交块 K=`0xdced693c`（**owner = 最后一个玩家实例 slot63**，全局单例）
+ 每玩家 78 字段块 + 13 字段外交修正块（K=`0x3a9f4f31`）。

### 3.1 主要文明（slot 0-5）关系表

met 列按行主序三角读法（映射未定证，见 §6）；rel = 双向对称存储的关系分（FP8）。

| 对 | met | 战争 | 开放边界(E0) | 开放边界(E2) | 关系分(E0=E2) |
|---|---|---|---|---|---|
| 俄罗斯 ↔ 波斯 | ✗(未定) | 无 | 无 | 无 | 0 |
| 俄罗斯 ↔ 阿拔斯 | ✓(未定) | 无 | 无 | 无 | 0 |
| 俄罗斯 ↔ 罗马 | ✗(未定) | 无 | 无 | 无 | 0 |
| **俄罗斯 ↔ 诺曼** | ✓(未定) | 无 | 无 | **俄→诺 ✓（唯一变化）** | **25.0** |
| 俄罗斯 ↔ 法兰西 | ✗(未定) | 无 | 无 | 无 | 0 |
| 波斯 ↔ 阿拔斯 | ✗(未定) | 无 | 无 | 无 | 0 |
| 波斯 ↔ 罗马 | ✗(未定) | 无 | 无 | 无 | 0 |
| 波斯 ↔ 诺曼 | ✗(未定) | 无 | 无 | 无 | 0 |
| 波斯 ↔ 法兰西 | ✗(未定) | 无 | 无 | 无 | 3.0 |
| 阿拔斯 ↔ 罗马 | ✗(未定) | 无 | 无 | 无 | 0 |
| 阿拔斯 ↔ 诺曼 | ✗(未定) | 无 | 无 | 无 | 11.0 |
| 阿拔斯 ↔ 法兰西 | ✗(未定) | 无 | 无 | 无 | 0 |
| 罗马 ↔ 诺曼 | ✗(未定) | 无 | 无 | 无 | 0 |
| 罗马 ↔ 法兰西 | ✗(未定) | 无 | 无 | 无 | 0 |
| 诺曼 ↔ 法兰西 | ✗(未定) | 无 | 无 | 无 | 0 |

- 开放边界在 E0 全文明 = "无" ✓（任务预期）；E2 俄→诺 = "有" ✓。
- 同盟/友谊/防御 pact：`IsAllied / IsPermanentlyAllied / IsInDefensivePact /
  HasDeclaredFriendship` 四个三角阵 + 每玩家 `HasNonAggressionPact`（64×u8）
  在 E0/E2 全 0 —— 无同盟 ✓。
- `Grievances / WarWeariness / NumWarsInitiatedAgainstPlayer / Favors`（64×u32）：
  全 0，唯一例外 slot0.Favors[4]=3000（对诺曼的支持度/恩惠，语义⚠️原值直读）。
- 关系分等级：游戏枚举 5 级（HOSTILE/UNFRIENDLY/NEUTRAL/FRIENDLY/HELPFUL，
  见 `diplomacy-gameeffects.xml`），分值→等级阈值未标定；现代档主流文明关系分
  90.0/89.0/81.0/70.5（有协议往来者）→ 0=中立、正分=逐级累积。

### 3.2 战争/和平（AtWar 矩阵）

- 矩阵 = `[count=2016=C(64,2)][2016×8B]`，元素默认全 0xff（无战争）。
- **E0/E2 实体 0-29 之间（含全部大文明×大文明、大文明×城邦、城邦×城邦）无任何条目
  = 全部和平** ✓（与 E0 游戏实况一致：仅 4 个侦察兵受伤，无正面战争）。
- 非默认条目 108 条，全部集中在行主序三角的行 40-57（每行恰 6 个连续列 j=i+1..i+6），
  元素 = `[u32 战争类型 hash 或 -1][u32 2]`，hash = `0x4396d725`（66 条）/ -1（42 条）；
  WarInitiator 元素 = `[u32 发起者][u32 2]`，**发起者 = 63−行号**（E0 11/18 行精确吻合：
  行41→22、行42→21、行45→18、行47→16、行48→15、行49→14、行50→13、行51→12、行55→8、
  行56→7、行57→6；现代档 9 行中 6 行吻合，其余为 -1/混合）。
- "63−行号"恰为城邦 slot 区间（6-23）→ 两种读法并存、均未定证：
  (a) 行主序 slot 直读：行 40-63 = 超界实体（疑似独立势力/部落槽），战争与真实玩家无关；
  (b) 实体 = 63−行号 的反转读法：行57 = 实体6 对 slots 5..0 的战争记录、行50 = 实体13 对
  slots 12..7——四个受伤侦察兵（slot0/2/4/10）恰好落在 (b) 的战争目标集合内，
  但城邦间 21 回合无任何单位伤亡又与 (b) 的"城邦互战"矛盾。未解（见 §7）。

### 3.3 外交修正值（尽力项）

13 字段块（每玩家 1 个，K=`0x3a9f4f31`）：`DiplomaticModifiers / OneSidedTradeValue /
BrokenPromises / KeptPromises / NoPromises / FirstImpressions` 均为
`[count=64][64×u32]` 数组（按对方 slot 索引）。**E0/E2 全部 64×6 数组逐值 = 0** ——
开局 21 回合无任何关系修正，与"关系分仅 25/11/3"自洽。另：`WarmongerScalingMultiplier`
FP8 = 1.0、`WarmongerScratchPlayer` = -1、`WarmongerScratchValue` = 0（无战狂记录 ✓）。

### 3.4 外交事件表（协议/努力/制裁记录）

- `ActiveDiplomacyEventsV2 = [count][事件×N]`，事件头 `[type_a][3][-1][1][1][F]` +
  需求 hash 列表；F=36/37（疑=需求条数）。事件边界可按 `[03][-1]` 模式切分，
  E2 的 5 条旧事件与 E0 逐字节一致（漂移未触及此块）。
- type_a → 动作名映射未标定；仅 **A=12 = 开放边界**（E2/E0 差分 + 字符串证据）。
  E0 活跃事件 A = 6,7,8,9,11；现代档 A = 0,1,4,19,22,23,25,26,28,29,31,32,33,34,35
  （15 条活跃，TotalDiplomacyEvents=38）。
- `ConcludedDiplomacyEvents`：E0=E2=7 条逐字节一致，事件头无 type_a（`[3][-1][1][1][F]`）。

---

## 4. E2/E0 差分总表（外交相关，raw 字节级）

| # | 块 | 字段/区域 | E0 | E2 | 结论 |
|---|---|---|---|---|---|
| 1 | 78f 块 slot0 | HasOpenBordersFrom | 64×00 | bit[4]=1 其余 00 | **开放边界状态位** |
| 2 | 15f 块 slot0 | DiplomacyBalance | 20480 (80.0) | 14080 (55.0) | −25 = 协议标价 |
| 3 | 18f 全局块 | TotalDiplomacyEvents | 12 | 13 | +1 事件 |
| 4 | 18f 全局块 | ActiveDiplomacyEventsV2 | [5][…3046B] | [6][…+615B 新事件 A=12] | 新协议记录 |
| 5 | body 字符串 | PLAYER_DIPLOMACY_OPEN_BORDERS_* | 无 | 3 条新增 | 协议需求/本地化键 |
| — | 其余 30 个 78f 块、31 个 15f/16f/13f 块、HasMet/AtWar/同盟矩阵、concluded 事件、deals 块 | — | — | 与 E0 一致 | 单操作差分 = 上表 4 处 |

（漂移说明：body 尺寸 9.57MB→11.3MB 的其余差异 = 对象图句柄整体漂移、单位/城市运行时
状态、字符串调色板增长等，非本次操作效果，符合任务警示。）

---

## 5. 工具用法

```bash
python3 -I tools/diplomacy.py <body.bin> <out.json>
# 输出: {source, war_block{total/max/active_count/concluded_count/events},
#        deals_block, players[{slot, alive, influence_balance, open_borders_to,
#        open_borders_ended_turn, relationship_level[64], grievances, favors,
#        war_weariness, token_handles{...}}],
#        pairs[{a,b,met,at_war,war_value,war_initiator,has_declared_friendship,
#               is_allied,in_defensive_pact,open_borders_a_into_b/b_into_a,
#               relationship_level_a/b}],
#        tribe_war_entries, diplomacy_modifier_blocks, tribe_blocks, unresolved}
```

实测：E0/E2 = 31 玩家、事件 5/6 条、开放边界出境对 0/1、战争对 0、解析失败 0；
MODERN = 19 玩家、活跃事件 15、开放边界出境对 11（8 对双向）、战争对 0。

---

## 6. 方法论备注

- 差分流程：先块级（31 玩家 × 6 类块按 owner 对齐）→ 字段级 raw hex diff → 唯一变化
  收窄到位级。E2/E0 的外交块组（78f/15f/16f/13f/3f/18f）除上表 4 处外逐字节一致，
  说明"退档重存漂移"主要落在对象图与单位/城市区，外交块是稳定差分面。
- 位方向验证用了三个独立证据源（E2 差分 + 现代档宗主 + l10n），避免把漂移当效果。
- `DIPLOMACY_ACTION_*` 定义串在存档 DB 快照中**不含 OPEN_BORDERS**（E0/E2 同表），
  开放边界相关定义以运行时字符串形式出现在 E2 的 bag 调色板区（0xabadda 附近，
  `[02][len][str][u32][…][字段名…TargetPlayerAccept/Amount/YieldType]` 结构）。

## 7. 未解项（如实）

1. **AtWar/HasMet 矩阵 (i,j)→玩家 slot 映射未定证**。行主序三角读法（工具采用）下
   实体 0-29 之间无战争条目（=和平，满足本轮需求）；但 WarInitiator=63−行 的强模式
   与四个受伤侦察兵的位置指向可能的"实体=63−行号"反转读法。两读法与"城邦 21 回合
   零单位伤亡"各有一处矛盾。下一步：找一局有明确宣战的存档（宣战回合已知）对齐矩阵
   元素与 WarInitiator。
2. **HasMet 元素 [u8 met][u32 X] 的 X 语义**：E0 X∈{1,2,3,4,12,14}（≤t21 可疑为首见
   回合），但现代档（t4）X=9 > 4 矛盾；且现代档大文明之间大多"未遇"（疑每时代重置）。
   三种候选布局（行主序/列主序/63 列跳过自身行）均无法同时满足"关系分非零⇒已遇"
   （E0 反例：波-法 3.0、阿-诺 11.0 未遇）与 FirstMeetIndexes（slot0 非零项 {4,9,18,22}，
   值 700/563/775/482，语义未解）。下一步：对象图反查 HasMet 引用对象 / 反汇编
   DiplomacyManager 序列化。
3. **type_a → 动作名映射**：A=12=开放边界已证；其余（6,7,8,9,11,0,1,4,19,…）未标定。
   下一步：按事件内需求 hash 集合与 DB 快照 RequirementSet 定义对齐。
4. **Token 数值直读**：Tokens/AvailableTokens = 对象句柄，引用链 2904→2903→122161/122162
   无 FP8 标量；顶栏余额由 DiplomacyBalance 直读（已解），但"令牌池/预约账本"的
   运行时结构未解（ReservationIds 空表、EscrowTokens 句柄）。
5. **关系分 → 5 级等级名阈值**：HOSTILE/UNFRIENDLY/NEUTRAL/FRIENDLY/HELPFUL 的分界
   未标定（XML 无数值，疑代码侧）。
6. **DiplomacyAgendas**（18f 块内，[6][含 slot 01-05 引用的 33B 记录×6]）与
   `RelationshipHistory`（872B，[64][变长记录]，记录含 hash `0xcbc93140`×4 + slot4 的
   5 事件记录）结构未解。
7. **Favors[4]=3000**：对诺曼的 3000 恩惠/支持度原值直读，语义（单向?）未对截图。
8. **AtWar 元素第二 u32**：E0 恒 2，现代档出现 1/19/24/16 —— 疑战争类型/时长，未解。

## 8. 验证锚点汇总

| 锚点 | 存档读数 | 真值 | 结论 |
|---|---|---|---|
| E0 顶栏影响力 80(+10) | slot0 DiplomacyBalance = 80.0 | 80 | ✓ |
| E2 开放边界后面板标价 25 | E2 余额 = 55.0 = 80−25 | −25 | ✓ |
| E2 与诺曼开放边界 | slot0.HasOpenBordersFrom[4]=1（唯一位变化） | 诺曼=slot4 | ✓ |
| E0 开放边界全文明=无 | 31 块 × 64 字节全 0 | 全无 | ✓ |
| E0 全文明和平 | AtWar 矩阵实体 0-29 无条目 | 无战争 | ✓ |
| E2 其余 29 玩家外交状态 | 逐字段 raw 一致 | 单操作差分 | ✓ |
| 现代档回归 | 19 玩家 0 解析失败；11 开放边界对（含宗主单向 3→6、2→11） | — | ✓ |
| 顶栏 80(+10) vs E2 余额 55 | 见 §1 注 | — | ⚠️ 截图时点/escrow 二义 |
