# Phase 2 — 城市完整化（字段映射 + 验证）

> 2026-11-09。工具：`tools/cities.py`（import 复用 `blockwalk.py`/`propertybag.py`）。
> 运行：`python3 -I tools/cities.py <body.bin> <out.json>`。
> 验证档：E0（远古 t21，俄罗斯人类 slot0，唯一城市圣彼得堡）+ 现代档 AutoSave_02_0004（t4，44 定居点）。
> 方法：E0 树逐字段定位 → 截图锚点标注语义 → 句柄反查对象图 → 现代档全量交叉验证。

---

## 1. 本轮新破解：bag 前对象图区的节点语法（部分）

Phase1 确认人口/产量等字段是对象句柄（U1），真值在 bagStart 之前的对象图区间（E0 ≈0x220000–0x2e35f8）。
本轮逆向出该区间的**节点记录形状**（ occurrence 级验证，非完整流语法）：

```
节点 = [tag u8][id u32][hashA u32][t2 u8] … [id-again u32]      ← id-again = 节点终止符
  t2 = 03: [hashB u32] + 载荷（至 id-again）
  t2 = 00: 载荷（至 id-again）
已确认的两类载荷:
  标量节点: 载荷 = u32 FP8（raw/256）      例: id 122087 → 00 04 00 00 = 4.0
  零值节点: tag=0x80, 无载荷               例: id 122089 → 值 0
  引用载荷: 若干 u32（指向其它节点 id）
```

- 标量节点值域实测 1.0–10.0（FP8 raw 256–2560），**没有**任何大值标量 ⇒ 面板级数值
  （食物 40、阈值 149、产量 174.6 等）只有 CurrentFood 这类"库存"直接落盘，
  产量/阈值是修正对象 DAG 运行时算出（与 U2 结论一致）。
- hashA/hashB 节点类语义未解（同一 class 的节点共享 hashA，如 7 个产量对象共用 5aa43615）。
- 节点流中混有链式记录 `[hash e248148c][00][idA][80][idB]`（双向链），语义未解。

`cities.py` 只用 occurrence 级形状匹配反查句柄值（标量/零值两种），不依赖完整流语法。

## 2. 字段映射表（城市实例块 0x0b0dacea/0x7a6d18c0，29 字段）

| 字段 | 编码 | 面板语义 | 证据字节（E0 圣彼得堡 / 现代雅典） | 状态 |
|---|---|---|---|---|
| Location | 0x400 blob8 (x,y) | 小地图坐标；plot = y×74+x | `2d000000 06000000`=(45,6)→plot489 / (41,36)→2705 | ✅ |
| Name | 0x400 blob `[01][len][LOC_CITY_NAME_*]` | 城市名 loc key | `15000000 LOC_CITY_NAME_RUSSIA1` | ✅ |
| HighestPopulation | blob4 | 人口总数 | `06000000`=6 / `26000000`=38 | ✅ |
| RuralPopulation | blob4 → 句柄 122087 | 乡村人口 | 句柄→图节点 FP8=4.0 | ✅ |
| UrbanPopulation | blob4 → 句柄 122088 | 市区人口 | 句柄→FP8=2.0 | ✅ |
| WorkerPopulation | blob4 → 句柄 122089 | 专家人口 | 零值节点 → 0 | ✅ |
| OverGrowthUnitPopulation | 句柄 | 过盈人口 | 零值节点 → 0 | ✅ |
| Population | 句柄（引用节点） | =Rural+Urban+Worker（引用分项对象） | 9 处引用无标量节点；总数用 HighestPopulation | ✅（间接） |
| NumRandomEventsFertility | 句柄 | 事件肥沃度 | 零值节点 → 0 | ✅ |
| ConnectedCitiesList | blob `[count][(u16,u16)×n]` | 连接定居点数 | `[0]` / `[9]`（雅典 9 连接） | ✅ |
| OwnerIDHistory | blob `[count][(slot,1,turn,hash)×n]` | 归属（见 §3） | 见 §3 | ✅ |
| AiId/DelayedDeath/HasBuildQueue/LastTurnDamaged/IsBeingRazed/RazeTurnModifier/LastTurnPurchase/NumDistrictsUnderSiege | 标量/blob | 运行时状态位 | 直读 | ✅ |
| FreeConstructibleTier / PendingPopulation / PendingGrowthEventBonusTriggers / UnlockedYieldChangeIdHashes / PreviousAgesOwnerIDHistory / AdditionalPurchasableConstructibleTag / ConstructiblePurchaseCharges / ConstructibleTagPurchaseCharges | blob4 | 待面板对账 | 直读（语义未逐一对截图） | ⚠️ 直读 |
| Components | 0x402 容器形 | 子组件流 | 遍历截断（Phase1 U3b 遗留） | ⚠️ 未定界 |

### 增长块（17 字段，hash 0x635c5324 成员键或 key=1 两种序列化形态，同 schema）

| 字段 | 面板语义 | E0 圣彼得堡 | 状态 |
|---|---|---|---|
| CurrentFood | 增长食物存量（FP8） | 10240 → **40.0** ✓（面板 40/149） | ✅ E0；现代档全 44 块=0（见 §6 疑点） |
| NextGrowthFoodThreshold | 面板"需要食物" | 句柄 122008（非数值） | ❌ U2 未解 |
| NextGrowthFoodThresholdBase | 阈值基数 | 句柄 139005 | ❌ U2 未解 |
| AllUnitTypesFoodMod / PercentGrowthAfterWorkerPlacement / PercentGrowthAfterRuralPlacement / NextGrowthFoodTresholdDiscount | 增长修正 | 句柄 122283–122286 连号批次 | ❌ U2 未解 |
| GrowthType | 增长模式 | CRC 型枚举 3168095966（非数值非句柄） | ⚠️ 原值直读 |
| TurnLastGrowth | 上次增长回合 | 19（≤t21 ✓）/ 现代档全 44 块=1 | ✅/⚠️ |
| CurrentStarvation / MigrationCityID / ProjectType / TurnLastNotifyStarving / TurnLastNotifyNearStarvationPanic / OverGrowthCount / lastTurnConsidered | 饥荒/迁移/项目 | 0 / 哨兵值 | ✅ 直读 |

### 幸福度块（19 字段）与产量统计块（50 字段）

| 字段 | 面板语义 | 状态 |
|---|---|---|
| Unhappiness / HappinessDeduction / SuplusHappiness / HappinessDeficit | 幸福"愉快"档值、+3/回合 | ❌ 句柄（122276/122277/122279/122280），面板分档值未还原 |
| OvercrowdingCount / GarrisonCount / SiegeCount / NoFreshWater / CanRevolt / TurnLastNotifyUnhappy | 运行时状态 | ✅ 直读（语义按名推断，未逐一对截图） |
| UnhappinessEffects | blob `[count][…]` | ⚠️ 直读，内部结构未解 |
| Yields / YieldIncomes / YieldDeductions / BuildingYields / …（26 个 `[7][句柄]` 列表） | 七项产量（食/锤/金/科/文/幸/影）每回合值 | ❌ 每产量 3 个对象 id → 修正对象 DAG，面板值运行时计算 |
| AdjacencyTypeFlatBonusV3 / *WarehouseYields* / ConstructibleYieldsMap / PlotYieldsMap / NaturalYieldsMapGA | 地块/仓库产量映射 | ⚠️ 结构可读（键=plot/类型 id，值=句柄列表），未对账 |

## 3. OwnerIDHistory 解码（本轮破解）

```
blob = [u32 count][count × (u32 slot, u32 1, u32 turn, u32 hash)]
  slot = 该事件后城市归属的玩家 slot
  turn = 事件回合（时代内回合，推断）
  hash = 事件类型：db081d9b=建城；ba0d0259?…（de340dba/c1c05902/51ee6893/edbb5496）=易主/征服类，细分未解
         ffffffff = 当前归属标记条目（slot 仍有效）
当前归属 slot = 最后一条目 slot；建城者 slot = 第一条目 slot
```

证据（现代档）：SPAIN1 = `[(5,…建城),(0,…t79 易主),(0,…标记)]` → 西班牙建、希腊（人类）夺、现属希腊 ✓；
FRENCH_EMPIRE7 = `[5→0→2]`（法建→希腊夺→夏威夷夺）✓；HAWAII1 = `[2→23→2→2]`（夏威夷建→独立势力 23 夺→夏威夷两度收复）✓。
同一玩家换时代换文明 → 城名池前缀随建城时代变化：slot1 = NORMAN*(探索时代建)+AMERICA*(现代时代建)。
**44 城归属分组零冲突**（slot0=希腊 11 城，slot1=美/诺曼 10 城，slot2=夏威夷/明治 8 城，slot3=桑海/埃及 11 城，slot4=印加 4 城）；
E0 六主文明 slot 0–5 与城名一一对应（俄罗斯=0=人类 ✓）。
城名池细节（同一文明跨时代选池、名号随机性）未解。

## 4. E0 圣彼得堡逐锚点验证

| 面板锚点 | 存档读数 | 结论 |
|---|---|---|
| 人口 6（市区2/乡村4/专家0） | HighestPopulation=6；Rural=4.0、Urban=2.0、Worker=0.0（句柄反查），和=6 | ✓ |
| 坐标（phase1 已验 plot 489） | Location=(45,6)→plot 489 | ✓ |
| 增长食物 40/149 | CurrentFood=40.0 ✓；149=句柄计算值 | ✓ / 149 ✗ U2 |
| +9 食物/回合 | 无落盘数值（产量 DAG） | ✗ 未解 |
| 13 回合后增长 | 依赖 149 与 +9 | ✗ 未解（公式 40+9×13≈149+2 自洽，见 phase1） |
| 幸福"愉快"（0~20 档）、+3幸福/回合 | Unhappiness/SuplusHappiness=句柄；无 0~20 值落盘 | ✗ 未解 |
| 无连接 | ConnectedCitiesList=[0] | ✓ |
| 归属=俄罗斯（人类 slot0） | OwnerIDHistory=[(slot0,t?,db081d9b)] | ✓ |
| （顶栏金30 = 玩家金库） | phase1 已验 GoldBalance=30.0 | ✓（玩家级，非本工具范围） |

## 5. 现代档（AutoSave_02_0004）逐锚点验证

| 面板锚点 | 存档读数 | 结论 |
|---|---|---|
| 雅典人口 38 | GREECE1 HighestPopulation=38 = Rural 17 + Urban 20 + Worker 1 | ✓ |
| 雅典分项 食174.6/锤52/金-6/科25/文36/幸43/影14 | 七项产量=修正对象 DAG，无落盘原值（全文搜 44697/44698 FP8 无命中） | ✗ 未解 |
| 斯巴达 食29/锤27/金38/科6/文4/幸28 | 同上（GREECE2，人口 12=9+3+0） | ✗ 未解 |
| 全局每回合（食531.1 等） | 玩家级产量（REPLAYDATASET 滞后一回合可查历史值；当回合值同样运行时算） | ✗ 未解（本工具范围外） |
| 金币 8585+385.9=8971 | phase1 已验（金库 FP8 8585） | ✓（玩家级） |
| 44 城按存档顺序，第一个=雅典 | 城组顺序=建城顺序，GREECE1 第一 | ✓ |
| 归属文明 | §3 分组零冲突；雅典/斯巴达 slot0=希腊（人类） | ✓ |

## 6. 44 城全量核对摘要

- **结构完整性**：44/44 定居点全部提取（城市实例+增长+幸福+产量四块一组，建城顺序排列）；41 城 `LOC_CITY_NAME_*` + 3 个独立势力 `LOC_INDEPENDENT_EXPLORATION_*`。
- **人口自洽**：44/44 满足 `乡村+市区+专家 == HighestPopulation` 且人口 > 0（雅典 38=17+20+1、斯巴达 12=9+3+0、埃及1 46=10+27+9、美国1 36=10+21+5、诺曼1 30=7+18+5 含 5 专家）。
- **归属自洽**：44/44 OwnerIDHistory 末条目 slot 与同 slot 城市组的城名池时代前缀一致，零冲突（§3）。
- **坐标**：44/44 位置在不同大陆呈聚类（希腊/埃及/桑海/印加各行段 vs 美/诺曼行 4–12），与地图行号上下颠倒的已知怪癖一致。
- **七项产量**：全部未解（见 §7），故"产量非负"检查不可做——如实标注。

全表（44 城，节选头尾；完整数据由 `cities.py` 输出 JSON）：

| # | 城 | 坐标 | 人口(总=乡+市+专) | 连接 | 归属 slot |
|---|---|---|---|---|---|
| 0 | GREECE1 雅典 | (41,36) | 38=17+20+1 | 9 | 0 |
| 1 | GREECE2 斯巴达 | (34,29) | 12=9+3+0 | 6 | 0 |
| 4 | SPAIN1 | (49,31) | 21=11+10+0 | 7 | 0（希腊夺） |
| 14 | AMERICA1 | (43,7) | 36=10+21+5 | 5 | 1 |
| 21 | HAWAII1 | (29,37) | 35=15+18+2 | 4 | 2 |
| 26 | INDEPENDENT_12 | (20,38) | 13=7+6+0 | 4 | 2（夏威夷夺） |
| 29 | SONGHAI1 | (39,4) | 22=9+10+3 | 6 | 3 |
| 34 | EGYPT1 | (29,12) | 46=10+27+9 | 8 | 3 |
| 40 | INCA1 | (17,20) | 36=16+18+2 | 2 | 4 |
| 43 | INCA6 | (11,16) | 11=7+4+0 | 2 | 4 |

## 7. 未解项（如实）

1. **七项产量每回合值**：`Yields[7]` 等 26 个列表存的是每项 3 个对象 id（如圣彼得堡 139097/139100/…，步长 3），
   指向修正对象 DAG（节点形状见 §1，最深 5+ 层引用链，叶子指向小 id 定义对象 2883–2911 等）。
   全文无 174.6/9.0 等 FP8 原值。下一步：游戏二进制反汇编 CityYields 求值函数，或按节点 class hash
   （5aa43615/25aab7a9/8af4a5ef/56d8628f…）聚类拟合算子。
2. **U2 增长阈值**（Phase1 遗留）：Threshold/Base/Percent/Discount 全为句柄；本轮反查确认它们指向
   DAG 节点而非数值（122008→refs{122009,122288}→…），无标量 149/4614。公式未还原。
3. **幸福度分档值**：Unhappiness/SuplusHappiness 为句柄；图中无 0~20 区间标量（标量值域 1–10）。
   "愉快"档与 +3/回合 的落盘来源未定位——可能同样运行时计算。
4. **现代档 CurrentFood 全 0 疑点**：44 块 CurrentFood=0、TurnLastGrowth=1（时代过渡 t1）。
   phase1 §6.4 的"雅典 42214=164.9"在当前 body_modern.bin 中**无法复现**（42214 全文仅 3 处 id 巧合）。
   原因未解：疑为时代过渡重置食物存量，或 phase1 当时读取的是另一存档文件。E0（无时代过渡）读数正常。
5. **建筑清单**：Constructibles 为 0x402 容器形（`[len=1][\x00]` 后无终止符），容器边界未定界
   （Phase1 U3b 遗留）；名人堂建造编年史逐城归属分隔符也未解。cities.py 如实输出 null。
6. **OwnerIDHistory 细节**：slot/归属已解；turn 字段为时代内回合的推断（个别城如 AMERICA1 x=1
   与"现代时代 t1 建城"吻合，但跨时代对齐未完全验证）；4 种易主事件 hash 的细分（征服/割让/叛乱）未解。
7. **城市名池**：同玩家跨时代换文明后城名池如何选定（建城时文明 vs 初始文明）未解。

## 8. 工具用法

```bash
python3 -I tools/cities.py <body.bin> <out.json>
# 输出: {"num_settlements": N, "cities": [{name, location, plot, population{highest,rural,urban,worker,sum},
#         growth{current_food,...}, happiness{...}, connected_settlements, owner{owner_slot, founding_slot, entries},
#         buildings, block_offsets}], "unresolved": [...]}
```
