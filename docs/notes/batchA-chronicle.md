# BatchA — 名人堂建造编年史逐城归属 + Founder 记录 (已破解)

> 2026-11-12。工具:`tools/chronicle.py`(CLI `python3 -I tools/chronicle.py <body.bin> <out.json>`)。
> 方法:E5.1(基线,t22)→E5.2(建城图拉,t22)干净差分定位新增段 + 游戏本体反汇编
> (`GameCore::GameSummary::{Object,ObjectDetails,DataPoint,DataPointValue,InternedString}::Read`,
> DataPointValue = `{u8 tag; u32 int?; InternedString}`)+ 四档交叉验证(E0/E5.1/E5.2/MODERN)。
> 结果:记录计数与块内声明前缀逐一相等(77/84/87/810),归属零冲突。

## 1. 块布局(名人堂 GAME_SUMMARY 第 2 块)

```
[06 00 00 00]['Player']×N            玩家对象表(6 条)
[04 00 00 00]['City']×M              城市注册表(M = 已注册定居点数)
[u32 dpCount]                        编年史 datapoint 条数(实测 77/84/87/810 全对上)
[dpCount × DataPoint]                ← 建造编年史事件流(逐城归属靠它)
[u32 seriesCount]                    尾部聚合序列条数(E0=146, E5.1=270, E5.2=273, MODERN=656)
[seriesCount × 序列记录]             每条 = [klen][键=指标名或城名][(u32 回合, u32 值)×当前回合数]
                                     (Gold/Culture/Science/Score/... 及 BUILDING_PALACE 等
                                     "按建造物计数"序列;与块1 REPLAYDATASET_* 同源,精确解析未做)
```

**"无分隔符"的真相:根本没有分隔符问题——每条 DataPoint 自带归属字段 f0**。

## 2. 城市注册表条目(分隔结构 = PRE u64 + 定长字段)

```
[u32 seq][u32 owner]                 ← 8B 前缀(属于本条;与下一条的 PRE 相接, 无任何分隔符)
[04 00 00 00]['City']
[u32 nameLen][名字]                  ← 可为 {LOC_CITY_NAME_X: ugc <id>;中文;} 玩家改名串
[u16 owner][u16 1][u16 idxA][u16 idxB]
[u32 plot]                           ← plot = y*74+x
[u64 0]
```

- `seq` = **城市对象 id(全局注册序号)**,编年史所有事件的归属键。
- `owner`(PRE 和 u16 两处)= **存档时归属**(SPAIN1=0=希腊夺后),不是建城者。
- `idxA/idxB` = 归属者名下注册序号(0 基/1 基,SPAIN1=4/5=希腊第 5 条注册)。
- 名字为**注册时快照**:时代换名城(AMERICA1 等被改名的 5 座)名字停留在旧池名,
  plot/owner 始终正确——对账时按 plot 而非名字(见 §5)。

**证据字节(E5.2,新增段=图拉)**:`0x9e14ef` 起 60B 插入
`0e 00 00 00 00 00 00 00 | 04 00 00 00 'City' | 15 00 00 00 'LOC_CITY_NAME_RUSSIA7'
00 00 01 00 01 00 02 00 | c4 02 00 00 | 00×8`
= PRE[seq=14][owner=0] + 名字 + [owner0][1][idxA1][idxB2] + plot 0x2c4=708 + u64 0;
其前 ABBASID2 条目尾部 8B 0 即上一条的 u64 0。E5.1 同位置 `0d 00 00 00 02 00 00 00`
= ABBASID2 的 PRE[13][2],差分插入边界由此逐字节锁定。

## 3. DataPoint(编年史事件记录)语法

```
[u32 keyLen][key][u32 f0][u32 f1][u32 valLen][val][u8 tag][i64]
tag=1 → i64 存在;tag=0 → 无 i64(Founder 记录, valLen=0)
```

反汇编依据:`DataPointValue::Read` 先读 1 字节 tag,tag==1 再读 u32 int,
最后必读 u32 InternedString;`DataPoint::Write` 写 f0/f1(+0x0/+0x4,+0x8 走不同 vtable 槽)
后写 Value。与存档字节完全吻合(含 `01 XX 00×7` = tag=1 + i64 小值)。

### 3.1 归属规则(逐城清单的钥匙)

| key | f0 含义 | val | i64 | 状态 |
|---|---|---|---|---|
| `TurnFounded` | 城 seq | 空 | **建城回合** | ✅ 与 REPLAYDATASET_TOTALCITIESBUILT 的 (civ,turn,256) 七城互证 |
| `City` | 城 seq | 空 | 建城回合 | ✅ 仅本局/当代新建城出现(E5.2 图拉=22;MODERN 无) |
| `BuildingsBuiltByType` | 城 seq | `BUILDING_*`/`IMPROVEMENT_*` | 疑=所在城区城内序号 | ✅ 归属;MODERN 326 建筑+242 改良全落在注册表 seq |
| `WondersBuiltByType` | 城 seq | `WONDER_*` | 1 | ✅ 归属(28 条) |
| `DistrictsBuiltByType` | 城 seq | `DISTRICT_*` | 1 | ✅ 但**只有预置城邦有记录**(MODERN 4 条;主文明城区不落盘) |
| `UnitsTrainedByType` | 城 seq | `UNIT_*` | 小整数 | ✅ 同上,仅城邦(MODERN 36 条全 f0≤12) |
| `UnitsLostByType`/`UnitsKilledByType` | 城 seq | `UNIT_*` | | ✅ 同上 |
| `Player` | 城 seq | 建造物/改良 | 1 | ✅ 玩家级行为(购买/赠与/大厅/迁都 palace×4)落在城 #f0;覆盖所有玩家 |
| `Religion` | 城 seq | 空 | 宗教 id | ✅ 该城改宗 |
| `LOC_RELIGION_*_NAME` | 城 seq | 城区/单位类型 | 1 | ✅ 宗教传播到该城对象;f0=0=改宗单位(无城归属, 1 条) |
| `LOC_CITY_NAME_X` | 建造物实例 lo-id(假设) | 城区类型 | ? | ⚠️ 键=注册表城名→按名归属;E5.x 7 条(见 §6) |
| `Founder` | 见 §4 | 空 | 无(tag=0) | ✅ 值结构已解 |

### 3.2 E5.2 图拉新增段(逐字节)

`dpCount 84→87`,新增 3 条:
```
1. [04]['City'][f0=14][f1=0][vlen=0][tag=1][i64=22]        ← 图拉建城标记(回合22)
2. [06]['Player'][f0=14][f1=0][12]['BUILDING_CITY_HALL'][tag1][1]  ← 图拉城市大厅
3. [13]['LOC_CITY_NAME_ROME1'][f0=1][f1=0][14]['DISTRICT_CITY_CENTER'][tag1][1]
   ← 图拉市中心(键=ROME1 之谜见 §6;归属经建造物实例序号交叉验证: E5.2 唯一新区
     = 俄罗斯 (7,8) = 图拉中心, progress.py 三档互证)
```
注册表 +1 条(§2 证据字节)。尾部序列 270→273(+3:DistrictsBuiltByType/UnitsTrainedByType/
IMPROVEMENT_QUARRY 各 +1 系列起点)。

## 4. Founder 记录值结构(悬案关闭)

`[07 00 00 00]['Founder'][u32 f0][u32 f1][00×13]` — 定长 32B,valLen=0、tag=0、无 i64。

- 仅 MODERN 出现 6 条:f0 = 2,4,6,8,10,12;**f1 = f0-1 恒成立**。
- 成对紧跟 `[TurnFounded][f0][i64=1]`。
- 判读:宗教创立标记(与游戏字符串簇 `Founder`/`HolyCity` 同簇,MODERN=宗教时代特性);
  f0/f1 疑为宗教对象 id 对 (hi, lo)——与建造物实例 (n,n+1) 对偶约定一致
  (6 条 = 6 个宗教; religion 事件里的 id=24 与键 LOC_RELIGION_SHINTO_NAME 相邻互证)。
  **f1 精确语义未定证**(见未解项)。
- save-format.md §3.2 旧假设"每个 City 记录后跟 [07]['Founder'] 建立者"**不成立**:
  城的"建立者"信息 = 注册表条目的 owner 字段(存档时归属);建城者需
  cross-check `cities.py` 的 OwnerIDHistory 首条目(Phase2 已解)。

## 5. 验证表(自检, validate 脚本 14/14 通过)

| # | 验证 | 结果 |
|---|---|---|
| 1 | E5.1→E5.2 前 7 城记录零变化(ROME1 辅键 +1=补录) | ✅ |
| 2 | 图拉段完整切出:RUSSIA7/(42,9)/plot708/owner0/回合22/city_hall | ✅ 对照任务锚点全中 |
| 3 | E5.2 新增 datapoint 恰 3 条(84→87),注册表恰 +1 | ✅ |
| 4 | E0/E2/E6/E7 编年史逐字节一致(退档重存不追加) | ✅ |
| 5 | MODERN 810/810 记录解析,计数=声明前缀 | ✅ |
| 6 | 49/50 注册表城按 plot 对上 cities.py,**owner 零冲突**;1 座已毁(HAWAII12) | ✅ |
| 7 | 事件总量:建筑 326 + 改良 242 + 奇观 28(全在注册表城) | ✅ |
| 8 | 抽查 3 城:GREECE1(22 建筑+1 奇观)/AMERICA1(22+8)/MEXICO4(新, 0) | ✅ |
| 9 | 预置城邦桶 = seq 1-10,12(无 11=零事件);Founder=6 条 | ✅ |
| 10 | 建城回合与 TOTALCITIESBUILT (civ,turn) 互证(E0 七城: 1,1,1,2,2,5,20) | ✅ |

MODERN 城数对账:注册表 50 + 预置 12 = 62 个 seq;现存 51(cities.py)
= 49 注册表现存 + 3 被俘城邦(仍用 INDEPENDENT 名) + 2 现代新刷独立势力 −
重合;已毁 = 1 注册城 + 9 预置城邦。名字按 plot 对账(42 城同名 = 新时代
t1 重注册 42/48 怪癖的镜像;8 城名字陈旧/玩家改名格式不同, plot+owner 全对)。
图拉 l10n:LOC_CITY_NAME_RUSSIA7 = 图拉 ✓(age-modern l10n)。

## 6. 未解项(如实)

1. **`[LOC_CITY_NAME_ROME1][1][DISTRICT_CITY_CENTER]` 的键为何是 ROME1**:
   经建造物实例序号交叉验证(E5.2 唯一新区=俄罗斯 (7,8)=图拉中心;罗马 slot3
   零新增)该记录描述的是**图拉**的市中心。键取注册表另一城的城名,且同族记录
   ([ROME1][3/5][DISTRICT_RURAL]、[FRENCH_EMPIRE1][4/5][UNIT_SETTLER])只在
   E5.1/E5.2 出现、MODERN 完全没有——疑为"对早期未写编年史条目的对象补录"
   (E0 保存于游戏更新前/时代截点),键=对象名、f0=每玩家实例 lo-id 为假设。
2. **Founder 的 f1**:=f0-1 恒成立,精确语义未定证(宗教对象 id 对/ holy city 关联)。
3. **BuildingsBuiltByType 等的 i64**(除 TurnFounded/City=回合已证):疑为建筑所在
   城区城内序号(GREECE1: GRANARY=1, WALLS=2, CAMP=3, WOODCUTTER=5, FARM=6),
   未逐一对图验证。
4. **主文明的城区/练兵不落盘于编年史**(只有城邦有 DistrictsBuilt/UnitsTrained):
   是设计如此还是写在别处未定位;城区清单仍以 runtime bag 为准(cities.py)。
5. **尾部序列的键规律**:E0/E5=逐玩家(指标名×6 玩家),MODERN 混入逐城
   (LOC_CITY_NAME_* 键);扫描计数 MODERN 336/656(stride 扫描长键对不齐),未逐条解析。
6. **`City` 建城标记出现条件**:E5.2 图拉(人类当回合建城)有,MODERN 当代建城
   (seq 61/62)无——疑"仅人类玩家/仅当回合"或与下一次保存时的改写有关,样本不足。

## 7. 工具用法

```bash
python3 -I tools/chronicle.py <body.bin> <out.json>
# 输出: players / cities[{seq,name,owner_slot,plot,location,founded_turn,
#   buildings,improvements,wonders,districts,units_trained,units_lost,
#   player_actions,religion_events,city_marker_turn,aux_namekey_events}]
# + city_states_unregistered(预置城邦) / founder_records / unmatched_records
# 校验: datapoint_count_parsed == datapoint_count_declared
```
