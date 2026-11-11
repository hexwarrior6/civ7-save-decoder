# civ7-save-decoder

文明7 (.Civ7Save) 存档逆向工具集。解析压缩体内的游戏数据：文明名单、科技/文化/金币产量曲线、战争历史、城市位置、建造编年史等。

> 目前没有任何公开工具能解析 Civ7 存档压缩体内的游戏数据。本仓库填补这个空白。

## 用 AI 分析你的存档

把下面这段话复制给你的 AI Agent（Claude、ChatGPT 等支持代码执行的工具），它会自动下载工具并分析你的存档：

```text
请帮我分析这个文明7存档文件。

按以下步骤操作：
1. 克隆工具仓库：git clone https://github.com/YOUR_USERNAME/civ7-save-decoder.git
2. 阅读 civ7-save-decoder/AGENTS.md 了解工具用法和已知限制
3. 运行 python3 civ7-save-decoder/tools/pipeline.py "我的存档文件路径"
4. 基于 AGENTS.md 中描述的数据格式，提取并分析：
   - 各文明实力排名（科技/文化/金/军事）
   - 战争历史与外交态势
   - 胜利路径建议（科技/军事/经济/文化四选一）
5. 给我一份完整的战局分析报告
```

> 将 `YOUR_USERNAME` 替换为实际的 GitHub 用户名，将 `"我的存档文件路径"` 替换为你的 .Civ7Save 文件路径。

## 解析进度

| 类别 | 状态 | 工具 |
|:---|:---:|:---|
| 容器解压 + 明文头部（文明名单/时代/回合/日期） | ✅ | pipeline.py |
| 名人堂数据集（科技/文化/金币/战争/夺城/奇观，每回合×每文明） | ✅ | pipeline.py / replay2.py |
| FXS 属性包二进制格式（VariantValue/DelineatedData） | ✅ | propertybag.py / blockwalk.py |
| 金币/影响力余额（每文明，FixedPoint<8>） | ✅ | blockwalk.py |
| 城市：人口分项（乡村/市区/专家）/坐标/归属历史/增长存量 | ✅ | cities.py |
| 单位：类型/归属/位置/HP/移动力/朝向/经验 | ✅ | units.py |
| 外交：开放边界位矩阵/影响力余额/关系分/战争矩阵 | ✅ | diplomacy.py |
| 科技树/传统/政体（CRC 反查到名字） | ✅ | progress.py |
| 建造记录（生产队列条目+建造物实例序号） | ✅ | progress.py |
| 地形/资源/生物群系/大陆/道路（逐格） | ✅ | terrain.py |
| 城市建筑/改良清单（逐城归属） | ⚠️ 70% | pipeline2.py |
| 遗产路径运行时 VP 值 / 每城七项产量分项 / 幸福分档值 | ❌ 运行时 DAG，不落盘 | — |
| 探索迷雾位图 / 当前研究方向科技名 | ❌ 未解 | — |

> ✅ 已完成 · ⚠️ 部分完成 · ❌ 未解 — 逐项详情见 [docs/parsing-status.md](docs/parsing-status.md)，逆向笔记见 [docs/notes/](docs/notes/)（Phase 1-6 逐阶段）

## 快速开始（手动）

```bash
git clone https://github.com/YOUR_USERNAME/civ7-save-decoder.git
python3 civ7-save-decoder/tools/pipeline.py "你的存档.Civ7Save"
```

## 仓库结构

```
├── AGENTS.md               # AI Agent 使用指南（自动被 AI 工具读取）
├── tools/                  # 解析脚本
│   ├── pipeline.py         # 一键解压 + 头部解析 + 数据集提取
│   ├── civ7parse.py        # 头部 chunk 格式解析器
│   ├── pipeline2.py        # 完整数据集提取（含战争/建筑/改良）
│   ├── replay2.py          # 名人堂 24 数据集独立解析
│   ├── propertybag.py      # FXS 属性包底层：CRC32 字典 + VariantValue 编解码
│   ├── blockwalk.py        # 属性包通用遍历器 → JSON 树
│   ├── cities.py           # 城市提取（人口分项/坐标/归属/增长）
│   ├── units.py            # 单位提取（类型/归属/位置/HP/移动力）
│   ├── diplomacy.py        # 外交提取（开放边界/关系分/战争/事件流）
│   ├── progress.py         # 科技/传统/遗产路径/生产/政策提取
│   ├── terrain.py          # 地图逐格提取（地形/资源/生物群系/道路）
│   └── fieldnames.txt      # 字段名 CRC32 反查字典（1200+ 名）
├── docs/
│   ├── save-format.md      # 二进制格式完整逆向笔记（§6 = FXS 属性包规范）
│   ├── parsing-status.md   # 解析进度详情（逐区域逐字段）
│   ├── notes/              # Phase 1-6 逐阶段逆向笔记（含证据字节）
│   └── modern-plan.md      # 基于本工具的实战对局规划示例
└── examples/               # 解压后的数据样本
```

## 文档

- **[存档格式逆向笔记](docs/save-format.md)** — 容器结构、chunk 格式、数据集编码、地理坐标、VP 计分、政策数值、FXS 属性包规范
- **[解析进度详情](docs/parsing-status.md)** — 按存档物理顺序的逐区域逐字段解析状态
- **[Phase 1-6 逆向笔记](docs/notes/)** — 每个阶段的破解方法、字段映射、证据字节、验证锚点
- **[实战规划示例](docs/modern-plan.md)** — 用本工具分析一局 135 回合对局的完整规划过程

## 已知限制

- 面板上的"运行时计算值"不落盘：每城七项产量分项、增长所需食物、幸福分档、遗产路径 VP——存档只存修正对象句柄（DAG），显示值由游戏引擎计算
- 探索迷雾位图未定位（每玩家只存已揭示计数）
- 当前研究方向科技的名字层未解（对象图节点→科技名映射缺钥匙）
- 城市建造编年史（名人堂区）逐城归属的分隔符仍未破解
- MODERN 测试档与实验档恰好同为 74×46 地图，stride 公式在不同地图尺寸下的普适性未测
