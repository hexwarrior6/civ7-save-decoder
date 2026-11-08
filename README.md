# civ7-save-tools

文明7 (.Civ7Save) 存档逆向工具集。解析压缩体内的游戏数据：文明名单、科技/文化/金币产量曲线、战争历史、城市位置、建造编年史等。

> 目前没有任何公开工具能解析 Civ7 存档压缩体内的游戏数据。本仓库填补这个空白。

## 用 AI 分析你的存档

把下面这段话复制给你的 AI Agent（Claude、ChatGPT 等支持代码执行的工具），它会自动下载工具并分析你的存档：

```text
请帮我分析这个文明7存档文件。

按以下步骤操作：
1. 克隆工具仓库：git clone https://github.com/YOUR_USERNAME/civ7-save-tools.git
2. 阅读 civ7-save-tools/AGENTS.md 了解工具用法和已知限制
3. 运行 python3 civ7-save-tools/tools/pipeline.py "我的存档文件路径"
4. 基于 AGENTS.md 中描述的数据格式，提取并分析：
   - 各文明实力排名（科技/文化/金/军事）
   - 战争历史与外交态势
   - 胜利路径建议（科技/军事/经济/文化四选一）
5. 给我一份完整的战局分析报告
```

> 将 `YOUR_USERNAME` 替换为实际的 GitHub 用户名，将 `"我的存档文件路径"` 替换为你的 .Civ7Save 文件路径。

## 解析进度

| 类别 | 状态 |
|:---|:---:|
| 容器解压 + 明文头部（文明名单/时代/回合/日期） | ✅ |
| 名人堂数据集（科技/文化/金币/战争/夺城/奇观，每回合×每文明） | ✅ |
| 城市坐标 + 名字翻译（plot 编码 + 本地化对照） | ✅ |
| 遗产路径 VP 计分定义 + 政策/传统效果数值 | ✅ |
| 城市建筑/改良清单（逐城归属） | ⚠️ 70% |
| 外交关系 / 遗产路径运行时进度 / 单位存量 | ⬜ 未解 |
| 地形地图 / 每城人口产出 / 宗教传播 | ⬜ 未解 |

> ✅ 已完成 · ⚠️ 部分完成 · ⬜ 未解 — 逐项详情见 [docs/parsing-status.md](docs/parsing-status.md)

## 快速开始（手动）

```bash
git clone https://github.com/YOUR_USERNAME/civ7-save-tools.git
python3 civ7-save-tools/tools/pipeline.py "你的存档.Civ7Save"
```

## 仓库结构

```
├── AGENTS.md               # AI Agent 使用指南（自动被 AI 工具读取）
├── tools/                  # 解析脚本
│   ├── pipeline.py         # 一键解压 + 头部解析 + 数据集提取
│   ├── civ7parse.py        # 头部 chunk 格式解析器
│   ├── pipeline2.py        # 完整数据集提取（含战争/建筑/改良）
│   └── replay2.py          # 名人堂 24 数据集独立解析
├── docs/
│   ├── save-format.md      # 二进制格式完整逆向笔记
│   ├── parsing-status.md   # 解析进度详情（逐区域逐字段）
│   └── modern-plan.md      # 基于本工具的实战对局规划示例
└── examples/               # 解压后的数据样本
```

## 文档

- **[存档格式逆向笔记](docs/save-format.md)** — 容器结构、chunk 格式、数据集编码、地理坐标、VP 计分、政策数值
- **[解析进度详情](docs/parsing-status.md)** — 按存档物理顺序的逐区域逐字段解析状态
- **[实战规划示例](docs/modern-plan.md)** — 用本工具分析一局 135 回合对局的完整规划过程

## 已知限制

- 城市详细记录（建筑/改良/奇观清单）的数据已定位，但逐城归属的分隔符解析未完成
- 运行时属性包（FXSBLKED）使用二进制序列化，外交/单位/人口/幸福度等数据未解出
- 地形/资源分布需要小地图截图辅助，存档内未直接解码
