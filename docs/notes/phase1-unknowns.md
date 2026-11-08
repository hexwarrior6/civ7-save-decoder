# Phase 1 — 三个未知项结题报告

> 全部结论基于 E0（回合21 基线）/E1（唯一操作=开拓者左移2格）实存字节 + 游戏二进制反汇编
> （`Serialization::DelineatedData::WriteSchema/WriteTerminator/IsBlockType/HasTerminator64`）。
> 现代档 AutoSave_02_0004（/tmp/civ7_analysis/body_modern.bin）作交叉验证。

---

## U1：size-4 块的 FixedPoint 值 vs 递增引用句柄 —— **已解决（规则 + 例外边界）**

### 结论

0x400/0x403 尺寸块的 4 字节负载统一语法是 `[u32 size][u32 payload]`，payload 的语义由
**字段在游戏 C++ schema 中的声明类型**决定，磁盘上无类型标签。经验判据（按可靠度排序）：

1. **句柄判据（强）**：payload ∈ 对象 id 值域，且该 u32 在存档"对象图区间"（E0 约
   0x220000–0x2e35f8）中作为节点 id 出现。实测句柄全部命中：
   - 增长块 NextGrowthFoodThreshold = `122008` → 图区命中 @0x2495f3、0x249608
   - AllUnitTypesFoodMod/PercentGrowthAfterWorker/…/Discount = `122283/84/85/86` → @0x24aac9…
   - 城市块六连号 122087..122092 → @0x249c9d 等
   - 单位块 FortificationTurnModifer=122439、AirInterceptionRange=122427 → 图区命中
2. **连号判据（强）**：同一块内相邻字段取连续值（±1..±3）⇒ 同一次对象分配批次的句柄。
   例：122283/84/85/86、105415..105420（现代档）、138173/138174/138198（单位 MovementChanges）。
3. **值判据（强）**：payload 与截图真值匹配 FP8：
   - CurrentFood = `10240` = **40.0** ✓（面板"增长食物 40/149"）
   - MovesRemaining = `768` = **3.0** ✓（面板移动力 3/3）
   - TurnLastGrowth = `19`（≤ 当前回合 21，整数语义）
4. **哨兵值**：`0` / `0xffffffff` 两读皆通（空对象句柄 = 空值），不参与区分。
5. **值域重叠警告**：句柄值域随存档对象总数增长（E0 ≈12.2万–15万，现代档 ≈10.5万–12万），
   与"大 FP8"（raw>65536 即 >256 食物/金币）在晚期存档会重叠 ⇒ **纯值域规则不可靠**，
   工具输出对 raw>65536 的 blob4 统一标注为 `ref?`（见 blockwalk.py 'blob4' 节点），
   由调用方按字段名二次判定（字典里的 FixedPoint 字段 = 值，其余 = 句柄）。

### 证据字节（E0 圣彼得堡增长块 @0x468c49）

```
CurrentFood               blob4 = 00 00 28 00  → 10240  = 40.0 FP8   （面板 40）
NextGrowthFoodThreshold   blob4 = 98 dc 01 00  → 122008 句柄（图区命中）
NextGrowthFoodThresholdBase blob4 = fd 1e 02 00 → 139005 句柄
AllUnitTypesFoodMod       blob4 = ab dd 01 00  → 122283 句柄 ┐
PercentGrowthAfterWorkerPlacement  ac dd 01 00 → 122284      ├ 连号批次
PercentGrowthAfterRuralPlacement   ad dd 01 00 → 122285      │
NextGrowthFoodTresholdDiscount     ae dd 01 00 → 122286      ┘
TurnLastGrowth            blob4 = 13 00 00 00  → 19（整数，≤当前回合21）
GrowthType                blob4 = de 4e d5 bc  → CRC 型枚举 hash（非数值非句柄）
```

顺带更正旧文档：现代档"105423..105428 连号"同为此类句柄批次，非"两种语义并存之谜"。

---

## U2：NextGrowthFoodThreshold ↔ 面板"需要食物" —— **旧换算假设证伪，机制已定位，公式未解**

### 结论

1. **CurrentFood 直接可读**：FP8，面板同值。E0 圣彼得堡 10240→40.0 ✓；现代档雅典
   t4 存档 42214→164.898 = 339.5−174.6 ✓（沿用旧验证）。
2. **NextGrowthFoodThreshold / …Base / …Discount 不是数值，是对象句柄**（U1 判据 1/2）。
   旧文档"411.97 ↔ 面板4614 求换算"的前提作废：411.97 只是句柄 105465 的 FP8 巧合读数。
3. 面板"需要食物"（E0=149，现代雅典=4614）= `city.Growth.getNextGrowthFoodThreshold().value`
   （游戏 UI 源码 model-city-details.js L264 实证），是**运行时用句柄引用的修正对象算出来的**：
   `149 × 256 = 38144` 与 `4614` 作为 u32/FP8 在两个存档中均**不存在**（已全文搜索）。
   即阈值不落盘，落盘的是 Base + 各 Percent/Discount 修正对象（句柄）。
4. E0 面板自洽校验：40 + 9×13 ≈ 149+2（+9食物/回合 × 13回合后增长 ✓）。

### 下一步（解公式或读运行值的路径）

- 在对象图区间按句柄 122008/139005 反查节点，解析修正对象的 Percent/Flat 值，复算
  `Base × (1+Percent) − Discount` 与 149 对账；
- 或直接 grep 游戏数据 `modules/age-antiquity/data/*.xml` 的增长曲线定义（GrowthSlope 等参数）
  拟合 两个锚点 (pop6→149, pop38→4614)。
- 未解状态：**部分解决**（字段语义 + 数据流已明；数值公式未还原）。

---

## U3：块值区与 schema 条目精确对位 —— **已解决（无未知 trailing 字节）**

### 结论

对位规则 = 按条目序、按类型定长消费，**不存在额外/缺失字节**。旧文档感知的"额外字节"
来自四个此前未识别的编码细节：

1. 0x402 字符串内容 **pad 到 4 对齐**后写 8B 终止符：`len=1` 的空串占 16 字节
   （`[01][00 00 00 00][FXSBLKED]`，@0xeaf364 现代档、@0x2e367c E0 双验证）。
2. 0x400/0x403 是 `[u32 size][size 字节]` 变长，老解析器按 4 字节读导致错位。
3. Bool（type 1）只占 **1 字节**（城市块 DelayedDeath @0x4680d9 = 单字节 0x00）。
4. 头部前置 u32（§2 的成员键/序号/流版本）被老解析器当成了值。

### 实测（E0 全量 + 抽样全解码）

| 块 | 条目数 | 对位结果 |
|---|---|---|
| 玩家金库 @0x464ca5 | 19 | 19/19 消费完，下一字节=下一结构 ✓ |
| 增长块（E0×7 / 现代档×44） | 17 | 17/17，尾部恰为 FXSBLKED ✓ |
| 城市实例 @0x467fcd | 29 | 29/29（含 blob8 Location=(45,6)、blob33 HasBuildQueue 内嵌城市名）✓ |
| 开拓者单位块 @0x46e707 | 47 | 前 46 字段全对位，末字段 Components 为容器形（见下）✓ |

`blockwalk.py` 全量统计：376 块完整消费（339 块尾部终止符确认）、0 块出现"剩余字节"。

### U3b（本轮新发现的遗留，如实入账）

0x402 有第二种**容器形**：`[len=1]["\x00"][pad]` 后**无终止符**，紧跟子块流
（每个子块自带 FXSBLKED），用于 Properties/Components/Controllers/Armies/Units/
TribeRelationships 等对象列表字段 —— 112/113 个 partial 块均止于此形。子块本身可遍历
（walker 重同步后继续走，因此 376 块中含大量组件块），但**容器的边界（子块数量）无计数前缀**，
零重扫无法确定容器终点 —— 下一阶段把容器形按"块序列 + 外层结构定位"处理。
