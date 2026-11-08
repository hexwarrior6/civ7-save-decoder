# civ7-save-tools

文明7 (.Civ7Save) 存档二进制格式的逆向工程工具集与格式文档。

## 这是什么

文明7 的存档是一个压缩的二进制容器，里面包含游戏运行时的完整状态：文明名单、每座城市的位置/建筑/改良设施、全游戏的建造编年史、名人堂数据集（每回合×每文明的科技/文化/金币/战争记录）等。

**截至 2026-11，没有任何公开工具能解析压缩体内的游戏数据**（GitHub 上的 [pydt/civ7-save-parser](https://github.com/pydt/civ7-save-parser) 只解析头部区块，[iqqmuT/civ7-save-editor](https://github.com/iqqmuT/civ7-save-editor) 只改金币/影响力）。本仓库填补这个空白。

## 已实现

| 工具 | 功能 |
|---|---|
| `tools/pipeline.py` | 一键解压存档 → 头部解析（文明名单/时代/回合）→ 名人堂数据集提取 |
| `tools/civ7parse.py` | 头部 chunk 格式解析器（5 区块组结构） |
| `tools/replay2.py` | 名人堂 24 个数据集解析（科技/文化/金币/战争/夺城/奇观/建城） |

## 已破解的格式（详见 docs/save-format.md）

- ✅ 容器压缩结构（zlib 分块）
- ✅ 头部 chunk 格式（文明名单、时代、回合）
- ✅ 名人堂数据集（24 个，每回合×每文明，×256 定点数）
- ✅ 城市注册表 + 坐标系统（plot = y×74+x，小地图校准方法）
- ✅ 遗产路径 VP 计分定义
- ✅ 政策/传统效果数值（游戏数据文件交叉验证）
- ⚠️ 城市详细记录（建筑/改良清单）——数据确认存在，逐城归属解析中
- ⬜ 二进制值结构（VariantValue 序列化）

## 快速开始

```bash
python3 tools/pipeline.py "你的存档.Civ7Save"
```

输出：时代/回合/日期、全部文明名单（人类/AI/存活）、名人堂数据集汇总。

## 文档

- [docs/save-format.md](docs/save-format.md) — 存档二进制格式完整逆向笔记
- [docs/modern-plan.md](docs/modern-plan.md) — 基于本工具的实战对局规划示例
