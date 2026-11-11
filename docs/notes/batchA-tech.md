# Batch A — 科技/市政进度：DB 节点哈希表 ↔ 组件注册表 对表 + 每文明进度提取

> 2026-11-12。工具：`tools/techlist.py`（import 复用 `progress.py` 的块解析器；CLI 同约定
> `python3 -I tools/techlist.py <body.bin> <out.json>`）。
> 输入：E0（远古 t21 基线）、E6（=E0+选科技 Writing）、E7（=E0+排产祭坛）、E2（=E0+开放边界）、
> E5.1/E5.2（t22）、MODERN（AutoSave_02_0027，现代档 t4）。
> 任务：把 DB 定义区的科技节点哈希表与 bag 内组件对象对上，产出每文明 科技/市政进度提取。

---

## 0. 结论（先说结果）

1. **DB 定义区的 NODE_TECH_*/NODE_CIVIC_* 哈希表已对上**：body 头部（bagStart 之前的 DB 区）
   有按**定义序**（=游戏 XML `<Types>` 行序）排列的 NODE_* CRC32 表。E0 中 16 科技节点表
   @0x13de5 = `NODE_TECH_AQ_AGRICULTURE … FUTURE_TECH`，与
   `age-antiquity/data/progression-trees-tech.xml` 的 Types 序**完全一致**；更大的 186/196 条
   混合表（属性节点+科技+市政+ORIGINS）@0x1739（E0）/0x1bed（MODERN）同理。
   名字层 = CRC32 反查（游戏本体 XML 全标识符 + fieldnames.txt，`techlist.py:load_node_names`）。
2. **bag 内每玩家"组件注册表"已解**（块层遍历器覆盖不到的 `0x0ab848ce` 记录族）：
   `[0x0ab848ce][kind u32][0a 00 0b 00][…]`，kind=2 科技节点对象（CRC=NODE_TECH_*、
   类CRC=SYSTEM_TECH）、kind=3 市政节点对象（NODE_CIVIC_*、SYSTEM_CULTURE）、
   kind=5 可解锁建筑对象（BUILDING_*）、kind=10 其它。记录体含
   `[06 00 00 00][f2 u32][f3 u32][u16 idx][u16 idx+1][01][ff ff ff ff][objid]`。
   f2=5（A 组：每科技 1 条 = 玩家树中"已实例化节点集"）/ f2=2（B 组：同一科技多条 =
   解锁行实例，AI 玩家大量出现）/ f2=10/1 变体（未定证）。
3. **`TargetTech` = 手动选择的研究方向**（语义修正 Phase5 的"恒 -1"）：现代档人类 slot0
   = `NODE_TECH_MO_MASS_PRODUCTION` ✓（与 LastCompletedNode=COMBUSTION 自洽），AI 玩家
   全 -1（自动研究不落盘，与 TargetCultureNode 人类有值/AI=None 完全同构）。
   **但远古档（含 E6 选科技）TargetTech 恒 -1** → 远古档选中方向未落盘（U-A2，证据链 §4）。
4. **"已完成科技全清单"无落盘列表**（U-A1）：科技块 8 字段只有 `LastCompletedNode`。
   工具输出 `completed_lower_bound` = LastCompletedNode 的前置闭包（从游戏 XML
   `ProgressionTreePrereqs` 计算）——下界；截图证明玩家可额外完成分支科技
   （E0 人类：闭包={AGRICULTURE,POTTERY}，截图已完成={农耕,航海,制陶,畜牧}），
   无任何已解结构存这个集合。
5. **Phase5 的 U5.2 修订**：E0→E6 的对象图 +38KB 不是"选科技"效果——
   E2/E5.1/E5.2/E6/E7 五份重存档的对象图**彼此只有 1 字节差异**（图尾计数器 0x8b/0x8c/0x8f），
   X/Y 两类节点（0x184ea6c8/0xae9ba3b4）在所有重存档中同为 434/434 条（E0 原档 217/217）
   → **+217/+217 是重存（re-save）漂移**，不是科技选择效果。

## 1. DB 定义区 CRC 序表（"哈希表"）的定位方法

`techlist.py:find_db_crc_tables`：先建 CRC32→名字反查字典（游戏 XML 全 `NODE_/TREE_/SYSTEM_/
BUILDING_/UNIT_/PROJECT_/DISTRICT_/TRADITION_/GOVERNMENT_` 标识符，约 28 万标识符），
然后在 `[0, bagStart)` 扫描所有命中 u32，向左右按 4 字节扩展成"连续命中段"，≥8 条即成表。
E0 实测两张表（`e0_tech.json:db_crc_tables`）：

| offset | 条数 | 内容 |
|---|---|---|
| 0x1739 | 186 | NODE_ATTRIBUTE_*（属性树+传奇）→ NODE_TECH_AQ_*(16) → NODE_CIVIC_AQ_MAIN_*(14) → 特色市政 → ORIGINS×20 |
| 0x13de5 | 16 | NODE_TECH_AQ_AGRICULTURE, POTTERY, ANIMAL_HUSBANDRY, SAILING, WRITING, IRRIGATION, MASONRY, CURRENCY, BRONZE_WORKING, WHEEL, NAVIGATION, ENGINEERING, MILITARY_TRAINING, MATHEMATICS, IRON_WORKING, FUTURE_TECH |

MODERN 同构（0x1bed=196 条、0x13f09=17 条 NODE_TECH_MO_*）。
表内条目按定义序排列，即"定义索引"——对象图/组件若以索引引用科技，此表即索引→名字映射。
本轮实测组件记录**直接存 CRC**（见 §2），未发现以定义索引引用的实例；索引语义保留给后续
对象图节点 class 破解（U-A3）。

## 2. bag 组件注册表（0x0ab848ce 记录族）——本轮新破解

位置：玩家实例块的 Components:402 容器内部（E0 slot0 起于 0x4769ca，slot0 区域共 533 条中的
~33 条；整个 bag 533 条 = 181×kind2 + 181×kind3 + 146×kind5 + 24×kind10 + 1×kind9）。
**不是** `[-1][1][1][count]` 块格式（块遍历器/Phase5 差分因此漏掉它——差分经 64B 窗口重扫补上）。

记录形状（kind=2/3，65B 标准长）：

```
[0xab848ce][kind=2][0a 00 0b 00][02 00 00 00][crc u32=NODE_TECH_*][01 00 00 00]
[244dc1f7=SYSTEM_TECH][idx u32(每玩家对象序号)][06 00 00 00][f2 u32][f3 u32]
[u16 idx][u16 idx+1][u64 0][03 00 00 00][递增计数器][01][ff ff ff ff][objid u32]
```

- kind=2 → 科技节点：crc 反查 NODE_TECH_*，类 CRC=SYSTEM_TECH(0x244dc1f7)；
- kind=3 → 市政节点：crc=NODE_CIVIC_*，类 CRC=SYSTEM_CULTURE(0xb77b07ec)；
- kind=5 → 建筑对象：crc=BUILDING_*（CITY_HALL/ACADEMY/GRANARY/…；E0 人类 16 栋、现代档 34 栋）；
- E0 人类 slot0 kind2 = 11 条 A 组(f2=5) + 1 条变体(f2=10, WHEEL, 尾部含
  PROJECT_CITY_SCIENCE_PROJECT CRC)；kind3 = 1 条（MYSTICISM=最后完成市政）；
- **A 组(f2=5)**：人类=每科技 1 条（E0 人类 11 条唯一，缺 SAILING/NAVIGATION/IRON_WORKING/
  FUTURE_TECH；现代档人类 6 条：STEAM_ENGINE/INDUSTRIALIZATION/MILITARY_SCIENCE/RADIO/
  NUCLEAR_FISSION/ACADEMICS）；AI 可含同科技多条（如阿拔斯 ANIMAL_HUSBANDRY×3）——
  语义判读为"树中已实例化/已揭示的科技节点"（与截图已完成集不重合，U-A3）；
- **B 组(f2=2) = 解锁行实例**：同一科技多条（MASONRY×2/3、MATHEMATICS×2、FUTURE_TECH×1…），
  仅 AI 玩家出现（E0 AI 各 19-23 条，人类远古档 0 条）——与 XML NodeUnlocks 行数的关系未对账（U-A3）；
- 尾部 `01 52fc23cf …`（罗马 AGRI/SAILING）等变体存在，字段未定证。

## 3. 科技块 TargetTech 语义修正（本轮关键发现）

`progress.py` 头注释与 parsing-status 曾记 "TargetTech 恒 -1"。本轮全 7 档 × 每 31/19 玩家复核：

| 存档 | slot0(人类) TargetTech | 判读 |
|---|---|---|
| E0/E2/E6/E7（远古 t21） | -1 | 无已提交研究方向 |
| E5.1/E5.2（远古 t22） | -1 | 同上（人类 SO 已被消耗=0.0，见下） |
| **MODERN（现代档）** | **NODE_TECH_MO_MASS_PRODUCTION** | **人类手动选择的方向 ✓** |
| MODERN AI×18 | -1 | 自动研究不落盘 |

与文化块完全同构：`TargetCultureNode` 人类=CODE_OF_LAWS（远古）/TABLE_OF_RANKS（现代档）、
AI=None。即 **TargetTech 是"正在研究"字段，AI 恒 -1；远古档人类选择未落盘（U-A2）**。

ScienceOverflow 的行为（旁证）：E0/E6/E7/E2（t21）slot0 SO=0.75；E5.1/E5.2（t22）slot0 SO=0.0、
LC 仍=POTTERY → 溢出 0.75 在下一回合被研究消耗，但目标节点在任何已解字段中都读不到。

## 4. E0↔E6↔E7 差分证据链（"选科技到底写了什么"）

方法：全 body 三角差分（图区 greedy 对齐 + bag 区块级对齐 + 词级 difflib）。

1. **图区（bagStart 之前）**：E0 与重存档第一处分歧 @0x2c92c8（+140B：E6 在链 0x23d72 后插入
   4 条 X/零类节点记录并改写链尾），第二处 @0x2e343c（+38,216B：图尾记录+大数组）。
   但 **E6↔E7 图区逐字节仅 1 处 8B 差异**（@0x2e5deb，图尾数组头 `[A][N]` 的 A：E6=0x8b(139)、
   E7=0x8c(140)；E2=0x8f(143)、E5.2=0x77(119)、E0=0x68(104)，N 亦随档波动 107→~7000/3098）
   → A/N 是易变运行时计数，**选科技在图区零落盘**。
2. **bag 区**：Phase5 175 块对齐差分 + 词级补扫（1368 hunk，其中组件区 228、字符串字典区 124、
   危机环形缓冲区 165、城市区 850=LOC 字典漂移）。**E6 独有变化只有 1 处**：11f 情报类块
   （CityId=[0x10001,-1]、Location=[-9999,-9999]、NumWalls/NumUrban/NumWonders）的
   **NumUrban 1→3**（NumWalls 句柄四档各不同=漂移；NumUrban 在 E7/E2 均为 1）。
   语义未定证（U-A4）；E7 独有=祭坛生产记录+Constructibles（已知）。
3. **明文头部**：E0↔重存档差异 = 存档文件名（UTF-16）+时间戳+版本串（E0↔E6 词级 329 hunk
   全部由此错位引起；E0↔E7 仅 6 hunk 同类）——无游戏状态。
4. **组件注册表**：E0↔E6 逐字节一致（含全部 kind2/3/5 记录与 objid）→ 选科技不增删组件。

**结论**：远古档"选中科技方向"不落入任何已解结构（块/组件/图静态记录/头部）。
已核对的旁证：MODERN TargetTech 有效 → 字段本身存在；E6 的选择疑似因"存档在回合结算前"
未提交（下一步可验证：取一份"选科技后过回合再存"的远古档看 TargetTech 是否写值）。

## 5. 每文明验证表（工具输出节选）

### E0（远古 t21，6 大文明）

| slot | 文明 | LastCompletedNode | 前置闭包(下界) | TargetTech | ScienceOverflow | 传统（文化块全反查） | A组科技节点 |
|---|---|---|---|---|---|---|---|
| 0 | 俄罗斯(人类) | NODE_TECH_AQ_POTTERY | AGRICULTURE, POTTERY | -1 | 0.75 | CHARISMATIC_LEADER, TOOL_MAKING, PRIESTHOOD | 11 |
| 1 | 波斯 | SAILING | AGRICULTURE, SAILING | -1 | 5.0 | +TRADITION_KARA | 6 |
| 2 | 阿拔斯 | SAILING | 同上 | -1 | 13.0 | CHARISMATIC_LEADER, TOOL_MAKING | 14 |
| 3 | 罗马 | POTTERY | AGRICULTURE, POTTERY | -1 | 0.0 | +TRADITION_AUXILIA_I | 10 |
| 4 | 诺曼 | SAILING | AGRICULTURE, SAILING | -1 | 15.0 | CHARISMATIC_LEADER, TOOL_MAKING | 7 |
| 5 | 法兰西帝国 | SAILING | AGRICULTURE, SAILING | -1 | 26.0 | +TRADITION_STYLE_EMPIRE_I | 4 |

市政：TargetCultureNode 人类=CODE_OF_LAWS、AI 各=SPADA/CHIEFDOM/EXERCITUS_ROMANUS/CHIEFDOM/
ORIGINS_FRENCH_EMPIRE；政府 DESPOTISM(人类)/CLASSICAL_REPUBLIC(AI)。

### E6（=E0+选科技 Writing）

块层/组件层/文化块与 E0 逐字节一致（§4）；科技块 TargetTech=-1。
**E6 截图锚点"选中=Writing"在存档中读不到** → U-A2 如实标注，不硬凑。

### MODERN（现代档 t4，19 玩家）

| 项 | 读数 | 判读 |
|---|---|---|
| slot0 TargetTech | NODE_TECH_MO_MASS_PRODUCTION | **正在研究=Mass Production ✓（字段有效）** |
| slot0 LastCompletedNode | NODE_TECH_MO_COMBUSTION | 闭包={STEAM_ENGINE, MILITARY_SCIENCE, COMBUSTION} |
| slot0 组件 A 组 | 6 条（STEAM_ENGINE/INDUSTRIALIZATION/MILITARY_SCIENCE/RADIO/NUCLEAR_FISSION/ACADEMICS） | 现代树 17 科技中已实例化 6 |
| slot0 传统 | 18 条全反查（XENIA_I…KRESTYANSKAYA_REFORMA_II） | 与 phase5 一致 |
| slot0 建筑 | 34 栋（GRANARY/FISHING_QUAY/LABORATORY/…） | kind5 组件全反查 |
| MODERN DB 表 | 0x13f09=17 条 NODE_TECH_MO_*（XML Types 序） | 科技清单规模自洽（17≥现代树行数） |

## 6. 未解项（如实）

1. **U-A1 已完成科技全清单**：无落盘 CRC 列表（文化块 UnlockedTraditions 的科技侧等价物
   不存在）。现有输出 = `LastCompletedNode` + XML 前置闭包（下界）。截图证明玩家可额外完成
   分支科技（E0 人类 SAILING/ANIMAL_HUSBANDRY），该集合在已解结构中读不到。
   下一步：反汇编 ProgressionTreePlayer 状态序列化，或找"完成分支科技前后"的差分档定位写点。
2. **U-A2 远古档正在研究方向**：E6 选科技全量差分后唯一独有变化=情报块 NumUrban 1→3
   （语义未定证）；TargetTech 在远古档不写值而现代档写值。下一步：①取"选科技后过一回合再存"
   的远古档验证 TargetTech 是否提交；②反汇编 TargetTech 写入路径；③查 NumUrban 块归属。
3. **U-A3 组件记录 f2 语义**：f2=5(A)/2(B)/10/1 与解锁行（XML NodeUnlocks）的对账未做；
   B 组为何仅 AI 出现未定证。
4. **U-A4 11f 情报类块**：CityId=[0x10001,-1]/[0x10004,0x10000] 的 id 编码（玩家/城序？）与
   NumUrban/NumWalls/NumWonders 计数语义未定证。
5. **U-A5 图尾 [A][N][ids…] 大数组**（E0 N=107 → 重存 ~7000/3098/5455 波动）：易变运行时
   结构，非科技清单；A 字节随操作 ±1（E7 祭坛 +1）但基数随重存大幅漂移。

## 7. 工具用法

```bash
python3 -I tools/techlist.py <body.bin> <out.json>
# 输出: {bag_start, num_players, players:[{slot, tech{last_completed_node_name,
#        completed_lower_bound, target_tech_name, science_overflow,...},
#        culture{unlocked_tradition_names, target_culture_node_name, ...},
#        components{groupA_techs, groupB_unlock_rows, buildings, ...}}],
#        db_crc_tables{tech_node_tables, civic_node_tables}, unresolved[]}
```

验证产物：`/tmp/scratch/e0_tech.json`、`/tmp/scratch/e6_tech.json`、`/tmp/scratch/modern_tech.json`。
fieldnames.txt 追加 354 名（DB 表 NODE_ATTRIBUTE_LEGEND_*/NODE_CIVIC_MO_*/TRADITION_*/BUILDING_*
等本轮反查，1315→1669 行）。
