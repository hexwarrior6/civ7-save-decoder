# AGENTS.md — AI Agent 使用指南

本仓库包含文明7 (.Civ7Save) 存档的逆向解析工具。AI Agent 应按本文件的指引使用这些工具。

## 你能做什么

解析文明7存档，提取以下数据用于战略分析：

- 文明名单（领袖/文明/人类AI/存活状态）
- 科技/文化/金币/分数 产量曲线（每回合×每文明，历史回放）
- 战争历史（宣战/夺城/失城）
- 奇观/建筑/城区 建造记录
- 城市坐标 + 名字（loc key 可经游戏本地化文件翻译）
- **每城人口**：总数 + 乡村/市区/专家分项 + 归属历史（44 城验证零冲突）
- **每个单位**：类型/归属文明/位置/HP/移动力/朝向/经验
- **每文明余额**：金币/影响力（FixedPoint<8> 直读，顶栏对账✓）
- **外交关系**：开放边界位矩阵/关系分/战争状态/外交事件流/影响力令牌
- **科技与传统**：已完成科技/已解锁传统/政体/所选市政（CRC 反查到名字）
- **生产记录**：每文明建造物实例清单（含正在排产条目，如 BUILDING_ALTAR）
- **地形地图**：逐格 地形/生物群系/大陆/特征/资源/道路（CRC 反查 100% 命中）
- 遗产路径 VP 计分定义 + 政策效果数值（定义层）

## 你不能做什么（不要编造）

以下数据在引擎里是**运行时计算的，存档只存对象句柄（DAG）**，如果用户问起请如实说明：

- 每座城市的七项产量分项（食/锤/金/科技/文化/幸福/影响力）——存档无标量值
- 城市增长"需要食物"阈值（面板 149/4614 等）——运行时由修正对象算出
- 幸福度分档值（"愉快"等档位对应的数值）
- 遗产路径的运行时 VP 进度值
- 当前正在研究的科技名（对象图节点→科技名映射未解，块层 TargetTech 恒 -1）
- 探索迷雾的具体格位（每玩家只存已揭示计数）
- 宗教传播状态
- 名人堂建造编年史的逐城归属（条目可读，分隔符未破解）

## 执行步骤

### 步骤 1：解压存档

```bash
python3 tools/pipeline.py "<存档绝对路径>"
```

输出：JSON 格式的元数据（时代/回合/日期）+ 文明名单 + 名人堂数据集，并把解压体写到 /tmp/civ7_analysis/body.bin。

### 步骤 2：按需跑专项提取器

```bash
python3 -I tools/blockwalk.py  /tmp/civ7_analysis/body.bin walk.json   # 属性包全量 → JSON 树
python3 -I tools/cities.py     /tmp/civ7_analysis/body.bin cities.json  # 城市（人口/坐标/归属）
python3 -I tools/units.py      /tmp/civ7_analysis/body.bin units.json   # 单位表
python3 -I tools/diplomacy.py  /tmp/civ7_analysis/body.bin dip.json     # 外交关系
python3 -I tools/progress.py   /tmp/civ7_analysis/body.bin prog.json    # 科技/传统/遗产/生产
python3 -I tools/terrain.py    /tmp/civ7_analysis/body.bin terrain.json # 地图逐格
```

### 步骤 3：读取格式文档

阅读 `docs/save-format.md` 了解：
- 数据集数值是 ×256 定点数（除以 256 得真实值）；属性包 FixedPoint<8> 同理
- 数据集 col 序号 = 文明 slot 序号（0 = 人类玩家）
- 回合轴 = 时代内回合（换时代后重置）
- FXS 属性包格式规范在 §6；各专项字段映射在 docs/notes/phase1-6 笔记

### 步骤 4：战略分析

基于提取的数据输出分析报告，应包含：
- 各文明实力排名（科技/文化/金/军事——用名人堂曲线+单位表+城市表）
- 战争状态与历史（宣战数据集 + diplomacy.py 战争矩阵）
- 胜利路径建议（科技/军事/经济/文化四选一）
- 威胁监控要点（AI 单位位置/边境城市/外交关系分）

## 已知怪癖（避免误判）

- 回放数据集的 col0 有一个 t0 垃圾值，跳过
- 数据集数值是 ×256 定点数；属性包 FP8 同理（raw/256）
- 新时代 t1 的名人堂只注册部分定居点（不是城市被毁）
- 名人堂的建造编年史中相邻城市记录无分隔符，逐城归属需谨慎
- 城市名是 loc key（如 LOC_CITY_NAME_GREECE1），实际名字需查游戏本地化文件
- 地图列号与游戏内东西方位直接对应；行号上下颠倒
- 地图东西环绕（圆柱形），南北不环绕
- size-4 块的 payload 有两种语义（数值 vs 对象句柄）：连号批次=句柄、与面板值对上=数值，判据见 docs/notes/phase1-unknowns.md U1
- 现代档增长块 CurrentFood 全为 0（换代重置），不要误判为解析错误
- 外交"开放边界"是 64×u8 位矩阵，bit[X]=X 对我开放（方向勿反）；位下标是 u8 非 u32
- E2 类退档重存档之间有 ~1.7MB 状态漂移，差分分析先看块级再收窄，勿把漂移当操作效果

## 文件说明

| 文件 | 用途 |
|---|---|
| `tools/pipeline.py` | 主入口：解压 + 头部解析 + 数据集提取 |
| `tools/civ7parse.py` | 头部 chunk 格式解析器 |
| `tools/pipeline2.py` | 完整数据集提取（含战争/建筑/改良） |
| `tools/replay2.py` | 名人堂 24 数据集独立解析 |
| `tools/propertybag.py` | FXS 属性包底层：CRC32 字典 + VariantValue 编解码 |
| `tools/blockwalk.py` | 属性包通用遍历器（容器展开，无静默丢字段） |
| `tools/cities.py` | 城市提取（人口分项/坐标/归属/增长存量） |
| `tools/units.py` | 单位提取（类型/归属/位置/HP/移动力/朝向） |
| `tools/diplomacy.py` | 外交提取（开放边界矩阵/关系分/战争/事件流） |
| `tools/progress.py` | 科技/传统/遗产路径/生产/政策提取 |
| `tools/terrain.py` | 地图逐格提取（地形/资源/生物群系/道路） |
| `tools/fieldnames.txt` | 字段名 CRC32 反查字典（1200+ 名） |
| `docs/save-format.md` | 二进制格式完整逆向笔记（§6=属性包规范） |
| `docs/parsing-status.md` | 解析进度逐项状态 |
| `docs/notes/` | Phase 1-6 逐阶段逆向笔记（含证据字节与验证锚点） |
