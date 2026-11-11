# Phase 5 — 科技/传统/遗产路径/生产/政策（三差分 + 全量结构）

> 2026-11-12。工具：`tools/progress.py`（import 复用 `propertybag.py` CRC/字典；块签名 =
> `[-1][1][1][count]` + schema 首条目 hash 严格定位，5/6-u32 双形式；blob 保留原始字节）。
> 运行：`python3 -I tools/progress.py <body.bin> <out.json>`。
> 输入：E0（远古 t21 基线）、E5.1/E5.2（t22，唯一操作=建城图拉）、E6（=E0+选科技）、
> E7（=E0+圣彼得堡排产祭坛）、E2（=E0+开放边界，phase4 已解）、MODERN（现代档回归）。
> 方法：三份"退档重存"档（E2/E6/E7）对 E0 做**玩家区逐块字节级对齐差分**（difflib 按
> (K,count,前5条目hash) 序列对齐 + 字段逐值比较），共同变化 = 重存漂移，独有变化 = 操作效果。

---

## 0. 截图锚点真值（先落盘）

| 截图 | 真值 | 存档侧对应 |
|---|---|---|
| `E6 科技树选择方向.png` | **选中科技 = 文字（Writing，`NODE_TECH_AQ_WRITING`，费用 125，显示 7 回合）**；已完成：农耕/航海/制陶/畜牧 | E6 块层无变化（见 §3）；选择记录在对象图（U5.2 未解到"名字"层） |
| `E7 城市生产项目.png` | 圣彼得堡"生产中"= 祭坛，⏱6；祭坛 = `BUILDING_ALTAR`（XML Cost=90） | E7 三处新结构均含 `BUILDING_ALTAR` CRC 0xFD4E5A4F（见 §4）；⏱6 为运行时显示值，存档无落盘 |
| `E0 遗产路径面板.png` | 文化 0 / 经济 0 / 军事 你=8·rank1 未相遇玩家 12·rank3 8 / 科技 0 | **8/12/8 与存档任何逐玩家统计不符**（E0 全图定居点最多 2，见 §5 U5.1） |
| `E0 遗产路径面板2.png` | 分数：你 950（rank2），rank1=960 | 分数公式（倒计时×1000 等）未逆向 |

**E6 选中科技名（按任务要求单独报告）**：`文字 / Writing / NODE_TECH_AQ_WRITING`。

---

## 1. 方法论：为什么 blockwalk 树差分不够、本用了什么

1. `blockwalk.py` 的容器形 0x402 截断点随漂移变化 → walk 树差分把"解析差异"当"内容差异"
   （E0↔E6 walk 差分 82 处，其中绝大多数为截断/对位伪差异）。
2. 本轮改用**严格原始解析**：对每对存档取"玩家 slot0 区间"（player0 块头 → player1 块头），
   用统一扫描器取出全部严格可解析块（E0=175 块），difflib 按 (K, count, 前5条目hash) 序列
   对齐后**逐字段比较原始字节**。结果可信：E0↔E6/E7/E2 三对均 175↔175 块全对齐。
3. 全局区（bagStart→player0，33 块）同法对齐：E0↔E6 零变化。
4. 对象图区（bagStart 之前）walk 覆盖不了 → 用**精确字节区间 diff**（4KB 粗扫 + 逐字节细分）
   定位 E6 的 +38KB 节点插入（见 §3）。

---

## 2. 差分 1：E5.1 → E5.2（唯一操作 = 开拓者建城"图拉"）

两档同为 t22（人类已行动），body 尺寸差 0.8%，walk 树差分 31 处，逐项核对后**全部为建城效果**：

| # | 变化 | 证据 |
|---|---|---|
| 1 | **新增城市组 15 块**（图拉）：城市实例 29f（`LOC_CITY_NAME_RUSSIA7` @(42,9) plot708、人口 2、HasBuildQueue=0）+ 建造 16f + 传统产量 3f + Districts 1f + 购买 15f + 增长 17f + 幸福 19f + 比较幸福 1f + 宗教 5f + 产量修正 11f + 项目类型 3f + 资源 13f + 贸易 6f + 产量 50f + 工人产量 11f | 与既有 7 城组同构 |
| 2 | **新增城区块**（18f，K=0/ctx=ffffffff）：`DISTRICT_CITY_CENTER` @(42,9)，CityID=0x00010000，Constructibles=[(1,7,8,0)] | 图拉中心 = 玩家序列第 8 个可建造物（宫0/圣彼得堡5城区1-5/祭坛6 → 7），证明 instance id 为**每玩家**序列 |
| 3 | **`UsedCityNames` 块**（b3b118c3 2f）新增一条 | 城名注册（游戏侧记录 RUSSIA7 已用） |
| 4 | 军事统计块（75f）slot0 `TownsFounded`: 0 → **1** | 建镇（图拉=镇）计数；`CitiesFounded` 保持 1 |
| 5 | 圣彼得堡城市实例 `ConnectedCitiesList`: [0] → [1]（条目 0x00020001） | 新定居点连入网络；条目值疑=图拉 id（U5.6） |
| 6 | 6 处 `acc95b3c`(11f) `NextID` 各 +2（135→137 等） | 对象图 id 分配器（新城区+城市对象） |
| 7 | 全局外交块（dced693c 18f）`TotalDiplomacyEvents` 12→13、`ConcludedDiplomacyEvents` 条数 +1 | **意外发现**：建城也写全局外交事件（内容未细究） |
| 8 | 开拓者单位实例：`DelayedDeath` 0→1、`Location`→(-10000,-10000) 哨兵、SightPlots 清空 | phase3 已证，复验 ✓ |
| 9 | **遗产路径块（15f）零变化** | 军事 VP（Pax Romana 定居点计分）为运行时值，不落盘（U5.1） |
| 10 | 生产记录：图拉出现前，圣彼得堡排产的祭坛记录不变（BUILDING_ALTAR, id(6,7)） | 见 §4 |

---

## 3. 差分 2：E0 → E6（唯一操作 = 选科技"文字"）

块层（玩家区 175 块 + 全局区 33 块，全对齐）：

- **科技块（d60fd288, 8f）零变化**：`TargetTech = -1`（E0/E6/E7/E2 ×31 玩家全部 -1）→ 该字段不存"当前研究"。
- E6 独有块变化仅 1 处：**已探明城市情报块**（11f）`NumUrban` 1→3、`NumWalls`/`NumWonders`（句柄）变化 —— 情报快照刷新，非科技语义。
- 与 E7/E2 共同的变化（=退档重存漂移）：`NumDistrictsOfType`（blob4→5 句柄）、`NextID` 124→135、`HistoricalLegacyPoints` 6 条目重排、情报块、危机 Countdowns/Trackers、`PointDetails`、7f 块 `Turn` 20→21。

**真身在对象图**：E6 的图比 E0 长 38,356B（bagStart 从 0x2e35f8 推移到 0x2ecbcc）。按
18B 节点形状 `[tag][id][hashA][t2=03][hashB][id-again]` 统计，新增恰好 **250 个零引用节点**：

| 新节点 class (tag, hashA, hashB) | Δ数量 | 判读 |
|---|---|---|
| (0x81, 0x184ea6c8, 0x396cdd54) | **+114** | ≈ 科技树解锁行数（age-antiquity `progression-trees-tech.xml` 的 NODE_TECH_AQ_* 解锁行 = 116）→ 判定 = 科技树解锁项实例化 |
| (0x81, 0xae9ba3b4, 0x8fb9d828) | **+134** | 同形态第二类（市政/依赖侧，未定证） |
| (0x00, 0x8b985166, 值=1) | +1 | 单例值节点（0x8b985166 在 DB 定义区有定义类，实例值=1） |
| (0x81, 0xbc7fd050, 0x7cd1540f) | +1 | 单例 |

**结论**：选科技不写任何块字段，而是在对象图实例化整棵科技树的解锁/依赖节点（约 250 个）。
节点以**定义索引**（非 CRC）引用科技——节点→科技名映射未解（U5.2）。因此
`progress.py` 的科技"当前研究方向"只能输出：截图锚点（文字）+ 块层数据（末完成节点等）。

科技/市政块的反查（本轮已解，见 §6）：`Tree=TREE_TECHS_AQ`、`LastCompletedNode=NODE_TECH_AQ_POTTERY`（人类末完成=制陶 ✓ 截图 4 个已完成之一）；文化块 `MainTree/ActiveTree=TREE_CIVICS_AQ_MAIN`、`LastCompletedNode=NODE_CIVIC_AQ_MAIN_MYSTICISM`、`TargetCultureNode=NODE_CIVIC_AQ_MAIN_CODE_OF_LAWS`（**所选市政 = Code of Laws，仅人类玩家有值**，AI 5 家 = None，原因未定证）、`ActiveGovernment=GOVERNMENT_DESPOTISM`（人类）/`GOVERNMENT_CLASSICAL_REPUBLIC`（AI 5 家）。

---

## 4. 差分 3：E0 → E7（唯一操作 = 圣彼得堡排产祭坛）

E7 独有变化（对齐差分 175↔175 块 + 间隙区扫描）共 3 处 + 1 处共漂移：

| # | 变化 | 位置 | 解读 |
|---|---|---|---|
| 1 | **城市中心城区块 Constructibles +1 条目** `(state=1, a=6, b=7, c=0)` | 18f 城区块 @(45,6)，E0=[(1,0,1,0)] → E7=[(1,0,1,0),(1,6,7,0)] | 祭坛进入"将建于市中心"的计划列表 |
| 2 | **"当前生产记录"** 新增：`BUILDING_ALTAR` + 城市坐标 (45,6) + 实例 id 对 (6,7)，以 FXSBLKED 结尾 | 宗教块(5f)→产量块(11f) 之间的间隙（0x402 容器内部，U3b 未定界） | 排产记录（E0 同位置为 UNIT_SETTLER 记录） |
| 3 | 资源块（926896f2 16f）`TurnLastConsidered`: -1 → 21 | E7 独有 | 资源结算回合被置为当前回合（疑重存副作用，未定证） |
| 4 | （共同漂移 7 处同 §3） | | |

**instance id 对 (a, a+1) 语义（本轮破解）**：`(lo, hi)=(n, n+1)` = **建造物实例序号**，每玩家一条序列：
圣彼得堡 宫殿=0、5 个城区=1..5、祭坛=6；图拉市中心=7（E5.2）。证据：E7(t21)/E5.1(t22)/E5.2(t22)
祭坛 id 恒 (6,7)——若是回合数会随时间递减；图拉 (7,8) 恰为序列下一项。截图 ⏱6 是运行时
显示值，**存档无"完成回合"落盘**（与产量 DAG 同理，U5.5）。

**排产计划的城区挂靠随存档变化**：E7 祭坛挂在市中心 [(45,6)]，E5.1/E5.2（同操作系，t22）
挂到市区 DISTRICT_URBAN (44,7) —— 计划位置为运行时重算值，未定证规则。

E5.1→E5.2 复核：祭坛记录/id 不变（建城不动生产），Tula 生产记录为空（HasBuildQueue=0）。

---

## 5. 全量结构（E0 + 现代档回归）

### 5.1 遗产路径块（15f，K=0x418d123e，ctx=2；每玩家 1 个）

字段（`python3 -I tools/progress.py` 输出 `legacy`）：

| 字段 | E0 读数 | 语义 |
|---|---|---|
| EnabledLegacyPaths | blob4=0（31 块全 0） | 启用路径位/句柄，**恒 0**（四路径默认全启用？无落盘开关） |
| LegacyPathEvents | blob4=0 | 事件列表，E0/现代档均空 |
| SettlementCountScoringItems | [2][16B×2]：`(1, 1, 2, 0x00010000)`、`(1, 1, 1, 1)`，第 3 个 u32 = **VP 2/1** | 军事路径两条计分规则定义：征服定居点 VP=2 / 非征服 VP=1 —— 与 DB `VICTORY_ANTIQUITY_MILITARY_CONQUEST/NONCONQUEST_SCORING` 的 VP=2/1 **吻合** |
| Settlement/Wonder/GreatWork/Resource/…ScoringItems | 空或 1 条（15~21B 不定长） | 各路径计分项定义（原样 hex 输出） |
| MilestonesAchieved | [12][12×(u32 hash, u8 flag=0)]，31 玩家一致；现代档为另一组 12 hash | 里程碑定义+达成位；**hash 无字符串可反查**（U5.4）；flag 全 0（E0 无人达成里程碑） |
| VictoryData | 104B 全 0 | 胜利数据（现代档亦全 0） |

**关键发现**：31 个遗产块只有 2 种内容（6 大文明有计分项模板 / 25 城邦+ID63 全空）——
该块是**逐玩家模板**，不含运行时 VP。**面板 VP 为运行时计算**：建城差分（E5.1→E5.2）中
遗产块零变化，唯一相关落盘 = 军事统计 `TownsFounded +1`。游戏文本（l10n）证实远古军事路径
= 帝国和平（Pax Romana）"12 座城镇或城市，被征服计 2"；DB 计分定义与之一致。
**E0 面板的 8/12/8 无法由存档数据解释**（全图定居点最多 2）→ U5.1。

军事 VP 代理（可从存档算）：`CitiesFounded + TownsFounded + 2×(征服定居点)`（征服系列字段
为句柄，E0=0）。E0 人类 = 1+0+0 = 1。

### 5.2 科技块（8f，K=0xd60fd288）与文化/传统块（33f，K=0x86eb5a88）

字段映射见 `progress.py` 头注释与输出 JSON。E0 全 6 大文明表：

| slot | 文明 | 末完成科技 | 科技溢出 | 末完成市政 | 所选市政 | 政府 | 传统 |
|---|---|---|---|---|---|---|---|
| 0 | 俄罗斯(人类) | NODE_TECH_AQ_POTTERY | 0.75 | NODE_CIVIC_AQ_MAIN_MYSTICISM | **NODE_CIVIC_AQ_MAIN_CODE_OF_LAWS** | DESPOTISM | CHARISMATIC_LEADER, TOOL_MAKING, PRIESTHOOD |
| 1 | 波斯 | NODE_TECH_AQ_SAILING | 5.0 | NODE_CIVIC_AQ_PERSIA_SPADA | — | DESPOTISM | + TRADITION_KARA |
| 2 | 阿拔斯 | NODE_TECH_AQ_SAILING | 13.0 | NODE_CIVIC_AQ_MAIN_CHIEFDOM | — | CLASSICAL_REPUBLIC | CHARISMATIC_LEADER, TOOL_MAKING |
| 3 | 罗马 | NODE_TECH_AQ_POTTERY | 0.0 | NODE_CIVIC_AQ_ROME_EXERCITUS_ROMANUS | — | CLASSICAL_REPUBLIC | + TRADITION_AUXILIA_I |
| 4 | 诺曼 | NODE_TECH_AQ_SAILING | 15.0 | NODE_CIVIC_AQ_MAIN_CHIEFDOM | — | CLASSICAL_REPUBLIC | CHARISMATIC_LEADER, TOOL_MAKING |
| 5 | 法兰西帝国 | NODE_TECH_AQ_SAILING | 26.0 | NODE_CIVIC_AQ_FRENCH_EMPIRE_ORIGINS | — | CLASSICAL_REPUBLIC | + TRADITION_STYLE_EMPIRE_I |

（科技树=TREE_TECHS_AQ 全员；传统数 2-3；`UnlockedTraditions`=CRC 列表全部反查成功。）
注：**"已完成科技列表"不存在落盘列表**——科技块只有 `LastCompletedNode`（最后完成），
完整完成集只能从对象图推（未解，U5.2 关联）。`ScienceOverflow` = FP8 直读（人类 0.75）。

### 5.3 政策卡块（8f，K=按 (count=8, ent1=AvailableCards) 识别）

`AvailableCards / Cards / NextCardID / LegacyPoints`：E0 全 0（远古时代无政策卡，卡=政策/
传统的运行时哈希态，与 save-format.md §3.6 预期一致）；`PlacementComplete`=01；
`HistoricalLegacyPoints` = [6][6×(u32 hash, u32 句柄)]——6 条与遗产路径相关的历史点数
（hash 未反查，U5.7；句柄 3664-3672 = 对象图小 id，重排=更新痕迹）。
**当前生效政策/传统激活集**：传统激活槽在文化块 `CultureSlots`（含传统 CRC——E0 人类槽内
= TOOL_MAKING；现代档槽内 = PRIMITIVE_ACCUMULATION + CITY_OF_PEACE，全部反查成功），
`NumActiveTraditions` 为句柄（数值运行时）。政策卡列表本身：远古档无、现代档
`Cards=0`（该存档的卡数据在对象图，未解——如实标注）。

### 5.4 生产（尽力项）

- **城区块**（18f，ent0=CityID）：`Constructibles = [count][count×(state u32, id_lo u16, id_hi u16, c u32)]`。
  E0 圣彼得堡 6 城区（CENTER+5 RURAL/URBAN），现代档 638 城区全解析。
- **当前生产记录**：每城"宗教块→产量修正块"间隙中的记录（type CRC + 可选坐标 + instance id 对）。
  E0：4 个大文明城 = UNIT_SETTLER（波斯/罗马/法兰西与人类都在产开拓者）；E7/E5.1/E5.2：BUILDING_ALTAR(6,7)。
  现代档 13 段记录（PORT/LABORATORY 等）。**局限**：记录在未定界容器内（U3b），按间隙模式
  提取，多项目队列只能部分还原。

### 5.5 现代档（AutoSave_02_0027 MODERN_body.bin）回归

- 19 玩家全部解析：科技 19/19、文化 19/19（传统全部反查，18 条/人）、遗产 19/19（模板一致）、
  金库 19/19、军事统计 19/19、城市 51、城区 638、生产记录段 13。
- 交叉验证：`MainTree=TREE_CIVICS_MO_RUSSIA`（slot0 现代文明=俄罗斯）、`TargetCultureNode=
  NODE_CIVIC_MO_RUSSIA_TABLE_OF_RANKS`、`LastCompletedNode=NODE_CIVIC_MO_RUSSIA_SERFDOM`、
  科技 `TREE_TECHS_MO`/`NODE_TECH_MO_COMBUSTION`、政府 `GOVERNMENT_ELECTIVE_REPUBLIC` ——
  与 phase2（slot0=希腊建城名池）+ 现代换文明（名池随时代）结论自洽。
- 城市名池在科技进步块/文化块均无冲突；51 定居点 > cities.py 的 44（walk 容器截断漏 7，
  本轮通配 K 扫描补全——cityinst K = 每文明模板 id，共 6 种 + 通配捕获）。

---

## 6. 名称反查（本轮新增）

- 方法：`NODE_/TREE_/TRADITION_/GOVERNMENT_/DISTRICT_` 从游戏本体 XML
  （`age-antiquity/data/progression-trees-*.xml` 等）grep + CRC32（同 phase3 §7 法）。
  **新名 108 个按字母序并入 `tools/fieldnames.txt`**（1207→1315 行）。
- 命中示例：`NODE_TECH_AQ_POTTERY`、`TREE_CIVICS_AQ_MAIN`、`TRADITION_TOOL_MAKING`、
  `GOVERNMENT_DESPOTISM`、`DISTRICT_CITY_CENTER`、现代档 `TREE_CIVICS_MO_RUSSIA`、
  `TRADITION_PRIMITIVE_ACCUMULATION` 等。
- 未命中：文化块 `Trees[]` 的第 2 棵树（E0 人类 = 0x0d52d83d，疑俄罗斯/领袖专属树，
  本地游戏文件无此名——DLC 或数据缺失）；`HistoricalLegacyPoints` 6 hash；里程碑 12 hash。

## 7. 未解项（如实）

1. **U5.1 遗产路径运行时 VP**：15f 块=模板无进度；面板 8/12/8 与存档任何逐玩家统计不符
   （定居点最多 2）。下一步：找一局"面板 VP 数值已知且较大"的存档对齐（例如完成奇观/文献后），
   或反汇编 LegacyPath 管理器；亦不排除 E0 截图摄于与存档发散的会话。
2. **U5.2 当前研究方向**：块层无字段；对象图 +250 节点（两类 class）以定义索引引用科技。
   下一步：扩展对象图节点语法（phase2 §1 基础上），把节点 payload 中的索引与
   `progression-trees-tech.xml` 的节点序对齐。
3. **U5.3 ScoringItems 条目语义**：SettlementCount 16B 条目的 4 个 u32 中仅第 3 个（VP）有
   DB 佐证；其余字段与各路径不定长条目未解。
4. **U5.4 里程碑 hash**：12 个（每时代一组）无字符串可反查。
5. **U5.5 生产队列完成回合**：无落盘原值；队列多项目结构在未定界容器内，只能按间隙模式
   提取当前/最近项。
6. **U5.6 城市/城区 id 编码**：城市实例 K=每文明模板对象 id（0x0b0dacea=俄罗斯等 6 种），
   ctx=玩家 slot；城区 CityID=0x00010000（圣彼得堡）与 ConnectedCitiesList 条目 0x00020001
   （图拉？）的编码规则未定证。
7. **U5.7 HistoricalLegacyPoints** 6 个 hash 与 `LegacyPoints` 句柄值未反查。
8. **建城写全局外交事件**（E5.1→E5.2 TotalDiplomacyEvents +1）原因未细究。

## 8. 工具用法

```bash
python3 -I tools/progress.py <body.bin> <out.json>
# 输出: {source, bag_start, num_players, players:[{slot, alive, tech, culture, legacy, gold,
#        milstats, cards, resources, settlements[], districts[], production_records[]}], unresolved[]}
```

验证产物：`/tmp/scratch/e0_progress.json`、`/tmp/scratch/modern_progress.json`
（另 E2/E5_1/E5_2/E6/E7 五份同构输出用于差分）。
