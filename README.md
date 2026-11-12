# civ7-save-decoder

文明7 (.Civ7Save) 存档逆向工具集。存档压缩体里的游戏数据——文明名单、逐回合产量曲线、战争史、城市、军队、外交、整张地图——目前没有公开工具能读，这套脚本把它们读了出来。

## 用 AI 分析你的存档

把下面这段话复制给你的 AI Agent（Claude、ChatGPT 等支持代码执行的工具），它会自动下载工具并分析你的存档：

```text
请帮我分析这个文明7存档文件。

按以下步骤操作：
1. 克隆工具仓库：git clone https://github.com/hexwarrior6/civ7-save-decoder.git
2. 阅读 civ7-save-decoder/AGENTS.md 了解工具用法和已知限制
3. 运行 python3 civ7-save-decoder/tools/pipeline.py "我的存档文件路径"
4. 基于 AGENTS.md 中描述的数据格式，提取并分析：
   - 各文明实力排名（科技/文化/金/军事）
   - 战争历史与外交态势
   - 胜利路径建议（科技/军事/经济/文化四选一）
5. 给我一份完整的战局分析报告
```

> 把 `"我的存档文件路径"` 换成你的 .Civ7Save 文件路径就行。

## 解析进度（字段级清单）

只统计存档里实际存了的数据。面板上那些现算的数——每城产量明细、涨人口还差多少粮、幸福档位——引擎不写盘，不在统计范围。

<table>
<thead>
<tr><th width="12%">类别</th><th width="40%">数据</th><th width="8%" align="center">状态</th><th>缺口说明</th></tr>
</thead>
<tbody>
<tr><td rowspan="2"><strong>基本信息</strong></td><td>时代 / 回合 / 日期 / 速度 / 难度 / 地图尺寸 / 对局编号</td><td align="center">✅</td><td>—</td></tr>
<tr><td>文明名单（领袖 / 文明 / 人类还是 AI / 存活 / 队伍）</td><td align="center">✅</td><td>—</td></tr>
<tr><td rowspan="6"><strong>历史记录</strong></td><td>逐回合 × 逐文明 科技 / 文化 / 金币 / 分数 曲线</td><td align="center">✅</td><td>—</td></tr>
<tr><td>宣战 / 夺城 / 失城 / 击杀（谁、哪回合）</td><td align="center">✅</td><td>—</td></tr>
<tr><td>奇观 / 建城 / 城区 / 建筑 累计数</td><td align="center">✅</td><td>—</td></tr>
<tr><td>建城顺序表（城名 + 坐标）</td><td align="center">✅</td><td>—</td></tr>
<tr><td>建造编年史（逐建筑逐改良）</td><td align="center">⚠️</td><td>条目全可读；相邻城记录没分隔符，逐城归属分不清</td></tr>
<tr><td>创始人记录</td><td align="center">⚠️</td><td>键已定位，值结构未解</td></tr>
<tr><td rowspan="3"><strong>城市</strong></td><td>位置 / 名字 / 归属（含易手历史）</td><td align="center">✅</td><td>—</td></tr>
<tr><td>人口三分项（乡村 / 市区 / 专家）</td><td align="center">✅</td><td>—</td></tr>
<tr><td>城市连接、粮食库存、当前排产任务</td><td align="center">✅</td><td>—</td></tr>
<tr><td rowspan="2"><strong>单位</strong></td><td>类型 / 归属 / 位置 / 血量 / 移动力 / 朝向 / 经验</td><td align="center">✅</td><td>—</td></tr>
<tr><td>单位等级 Level</td><td align="center">⚠️</td><td>是个对象编号，没解出数值</td></tr>
<tr><td rowspan="4"><strong>外交</strong></td><td>开放边境（逐对）/ 关系分 / 影响力余额与令牌</td><td align="center">✅</td><td>—</td></tr>
<tr><td>同盟 / 宣布友谊 / 防御条约状态位</td><td align="center">✅</td><td>—</td></tr>
<tr><td>外交动作流水</td><td align="center">⚠️</td><td>动作类型目前只认出"开放边境"一种</td></tr>
<tr><td>战争状态矩阵</td><td align="center">⚠️</td><td>数据在；行列对应哪个文明还没定死</td></tr>
<tr><td rowspan="4"><strong>科技与文化</strong></td><td>政体 / 所选市政 / 已解锁传统 / 科研溢出</td><td align="center">✅</td><td>—</td></tr>
<tr><td>最后完成的科技 / 市政</td><td align="center">✅</td><td>—</td></tr>
<tr><td>已完成科技全清单</td><td align="center">⚠️</td><td>只读出最后完成的一个</td></tr>
<tr><td>正在研究的科技名字</td><td align="center">❌</td><td>存档里只有一串编号</td></tr>
<tr><td rowspan="6"><strong>地图</strong></td><td>每格 地形 / 生物群系 / 大洲 / 地貌 / 道路 / 海拔</td><td align="center">✅</td><td>—</td></tr>
<tr><td>资源分布（26 种逐格）与自然奇观位置</td><td align="center">✅</td><td>—</td></tr>
<tr><td>每格有无单位 / 城市</td><td align="center">✅</td><td>—</td></tr>
<tr><td>迷雾：每玩家逐格已探索位图</td><td align="center">✅</td><td>计数与位图位数的精确换算没弄清</td></tr>
<tr><td>每格标志位（u14 / u18 / u39 / 尾区间）</td><td align="center">⚠️</td><td>u42/u47/u17/u16 已定证；其余原样输出</td></tr>
<tr><td>视野区剩余结构 + 静态区 375 KB</td><td align="center">⚠️</td><td>迷雾数组已从视野区解出；其余 ~30KB/玩家未解</td></tr>
<tr><td rowspan="3"><strong>其他</strong></td><td>玩家资源库存（手里有什么 / 哪些城在用）</td><td align="center">✅</td><td>个别类别标签对不上 XML</td></tr>
<tr><td>宗教</td><td align="center">⚠️</td><td>单位宗教块在；城市传播没做</td></tr>
<tr><td>字符串调色板（7 段 × 41 KB）</td><td align="center">❌</td><td>未解</td></tr>
</tbody>
</table>

战略分析要用的主干——历史曲线、城市、军队、外交、地图——都已读出。⚠️/❌ 项的下一步路径写在 [docs/parsing-status.md](docs/parsing-status.md) 和 [docs/notes/](docs/notes/) 里。

## 快速开始（手动）

```bash
git clone https://github.com/hexwarrior6/civ7-save-decoder.git
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

存档不记面板上的所有数。每城"+9 粮 +5 锤"这类明细、涨人口还差多少粮、幸福档位，都是引擎开面板时现算的，存档里只留了计算要用的零件，没有结果——读不出来不是工具的问题，是本来就没存。硬骨头还剩几块：迷雾只有个"开了多少格"的计数，位图没找到；正在研究的科技在存档里是一串编号，对不上名字；地图解析只在 74×46 的图幅上验证过，别的尺寸还没试。
