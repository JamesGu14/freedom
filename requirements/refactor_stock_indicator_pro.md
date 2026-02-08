# 重构需求：使用 TuShare stk_factor_pro 替换自计算指标

## 1. 背景

### 1.1 现状
当前个股技术指标由 `calculate_indicators.py` 本地计算，存储在 Parquet 文件中（`data/features/indicators/`），通过 DuckDB 读取后供 API 和策略使用。

**现有指标字段**（19个）：
| 类别 | 字段名 | 参数 |
|------|--------|------|
| 均线 | `ma5`, `ma10`, `ma20`, `ma30`, `ma60`, `ma120`, `ma200`, `ma250`, `ma500` | 对应周期 |
| MACD | `macd`, `macd_signal`, `macd_hist` | SHORT=12, LONG=26, M=9 |
| RSI | `rsi` | N=14 |
| KDJ | `kdj_k`, `kdj_d`, `kdj_j` | N=9, M1=3, M2=3 |
| BOLL | `boll_upper`, `boll_middle`, `boll_lower` | N=20, P=2 |

### 1.2 目标
使用 TuShare `stk_factor_pro` 接口（[文档](https://tushare.pro/document/2?doc_id=328)）直接获取专业版技术因子数据，替换本地计算逻辑。

**好处**：
- 减少本地计算开销（当前全量计算耗时长）
- 获得更多指标（ATR、CCI、DMI、WR、TRIX 等），无需自行实现
- 数据质量由 TuShare 社区维护，减少 bug 风险
- 同时获取前复权/后复权/不复权三种版本

### 1.3 接口说明
- **接口名**：`stk_factor_pro`
- **积分要求**：5000 积分
- **限量**：单次最多 10000 条，可按日期循环
- **文档**：https://tushare.pro/document/2?doc_id=328

---

## 2. 字段映射

### 2.1 现有字段 → stk_factor_pro 字段对照

| 现有字段 | stk_factor_pro 对应字段（前复权） | 说明 |
|---------|-------------------------------|------|
| `ma5` | `ma_qfq_5` | 简单移动平均 N=5 |
| `ma10` | `ma_qfq_10` | 简单移动平均 N=10 |
| `ma20` | `ma_qfq_20` | 简单移动平均 N=20 |
| `ma30` | `ma_qfq_30` | 简单移动平均 N=30 |
| `ma60` | `ma_qfq_60` | 简单移动平均 N=60 |
| `ma120` | - | stk_factor_pro 无 MA120，需保留自算或用 EMA 替代 |
| `ma200` | - | stk_factor_pro 无 MA200，需保留自算或用 MA250 替代 |
| `ma250` | `ma_qfq_250` | 简单移动平均 N=250 |
| `ma500` | - | stk_factor_pro 无 MA500，需保留自算或放弃 |
| `macd` | `macd_dif_qfq` | MACD DIF 线 (SHORT=12, LONG=26, M=9) |
| `macd_signal` | `macd_dea_qfq` | MACD DEA 信号线 |
| `macd_hist` | `macd_qfq` | MACD 柱状图（注意：API 字段名叫 macd，实际是柱状图） |
| `rsi` (N=14) | - | stk_factor_pro 提供 RSI(6/12/24)，无 RSI(14)，需取 `rsi_qfq_12` 或保留自算 |
| `kdj_k` | `kdj_k_qfq` | KDJ K 线 (N=9, M1=3, M2=3) |
| `kdj_d` | `kdj_d_qfq` | KDJ D 线 |
| `kdj_j` | `kdj_qfq` | KDJ J 线（API 字段名叫 kdj） |
| `boll_upper` | `boll_upper_qfq` | 布林带上轨 (N=20, P=2) |
| `boll_middle` | `boll_mid_qfq` | 布林带中轨 |
| `boll_lower` | `boll_lower_qfq` | 布林带下轨 |

### 2.2 已确认的字段决策

| 问题 | 决策 |
|------|------|
| MA120/MA200/MA500 不在 API 中 | **放弃**，不再保留（当前无策略/前端使用） |
| RSI(14) 不在 API 中，API 提供 RSI(6/12/24) | **改用 RSI(12)**（`rsi_qfq_12`），策略代码中 `rsi` → `rsi12` |

### 2.3 新增可用指标（可选启用）

stk_factor_pro 额外提供但当前未使用的指标：

| 指标 | 字段（前复权） | 说明 |
|------|---------------|------|
| ATR | `atr_qfq` | 真实波动 N=20 |
| CCI | `cci_qfq` | 顺势指标 N=14 |
| DMI | `dmi_pdi_qfq`, `dmi_mdi_qfq`, `dmi_adx_qfq`, `dmi_adxr_qfq` | 动向指标 |
| WR | `wr_qfq`, `wr1_qfq` | 威廉指标 N=10, N1=6 |
| TRIX | `trix_qfq`, `trma_qfq` | 三重指数平滑 |
| EMA | `ema_qfq_5/10/20/30/60/90/250` | 指数移动平均 |
| OBV | `obv_qfq` | 能量潮 |
| ROC | `roc_qfq`, `maroc_qfq` | 变动率 |
| 连涨/连跌 | `updays`, `downdays` | 连涨/连跌天数 |
| 估值 | `pe`, `pe_ttm`, `pb`, `ps`, `ps_ttm` | 市盈率/市净率等 |
| 换手率 | `turnover_rate`, `turnover_rate_f`, `volume_ratio` | 换手率/量比 |

---

## 3. 复权版本选择

stk_factor_pro 对每个指标提供三种复权版本：
- `_bfq`：不复权
- `_qfq`：前复权
- `_hfq`：后复权

**建议**：统一使用 **前复权（`_qfq`）** 版本，与当前 K 线图展示一致。

---

## 4. 改动清单

### 4.1 后端脚本改动

#### 4.1.1 新增 TuShare Client 函数
**文件**：`backend/app/data/tushare_client.py`

```python
def fetch_stk_factor_pro(
    *,
    trade_date: str,
    fields: str = "",
) -> pd.DataFrame:
    """
    获取股票技术面因子数据（专业版）
    按 trade_date 调用，一次返回全市场约 5000 只股票的因子数据（<10000 条限制）。
    """
    pro = ts.pro_api(settings.tushare_token)
    df = pro.stk_factor_pro(
        trade_date=trade_date,
        fields=fields,
    )
    return df if df is not None else pd.DataFrame()
```

#### 4.1.2 新增每日同步脚本
**文件**：`backend/scripts/daily/sync_stk_factor_pro.py`

**核心调用策略**：每次传入 `trade_date`，一次 API 调用返回该日全市场约 5000 只股票的因子数据，远低于单次 10000 条限制。即 **1 个交易日 = 1 次 API 调用**。

**功能**：
- 遍历目标日期范围内的交易日，逐日调用 API
- 只保留需要的字段（见 4.1.3）
- 重命名为统一的内部字段名
- 按 `ts_code` 分组，写入 Parquet 文件（沿用现有分区结构）

**命令行参数**：
```bash
# 同步指定日期（1 次 API 调用）
python backend/scripts/daily/sync_stk_factor_pro.py --trade-date 20260206

# 同步最近 N 天（N 次 API 调用，跳过非交易日）
python backend/scripts/daily/sync_stk_factor_pro.py --last-days 1

# 同步日期区间（遍历区间内的交易日，每日 1 次调用）
python backend/scripts/daily/sync_stk_factor_pro.py --start-date 20260101 --end-date 20260206
```

**频率控制**：
- 5000 积分每分钟最多 30 次请求
- 每次调用传入 `trade_date`，1 天 = 1 次调用
- 拉取前查 `trade_calendar`，自动跳过非交易日
- 批量拉取时默认每次调用间隔 2 秒（`--sleep 2`），确保不超频

#### 4.1.3 字段选择与重命名

从 API 拉取时只请求需要的字段（减少传输量），并重命名为内部字段名：

```python
# 请求的 API 字段
API_FIELDS = ",".join([
    "ts_code", "trade_date",
    # 价格（前复权）
    "close_qfq",
    # MA
    "ma_qfq_5", "ma_qfq_10", "ma_qfq_20", "ma_qfq_30", "ma_qfq_60", "ma_qfq_90", "ma_qfq_250",
    # MACD
    "macd_dif_qfq", "macd_dea_qfq", "macd_qfq",
    # KDJ
    "kdj_k_qfq", "kdj_d_qfq", "kdj_qfq",
    # BOLL
    "boll_upper_qfq", "boll_mid_qfq", "boll_lower_qfq",
    # RSI
    "rsi_qfq_6", "rsi_qfq_12", "rsi_qfq_24",
    # 额外有用指标
    "atr_qfq", "cci_qfq",
    "wr_qfq", "wr1_qfq",
    "updays", "downdays",
    # 估值/换手
    "pe", "pe_ttm", "pb",
    "turnover_rate", "turnover_rate_f", "volume_ratio",
])

# 重命名映射（API 字段 → 内部字段）
RENAME_MAP = {
    "ma_qfq_5": "ma5",
    "ma_qfq_10": "ma10",
    "ma_qfq_20": "ma20",
    "ma_qfq_30": "ma30",
    "ma_qfq_60": "ma60",
    "ma_qfq_90": "ma90",
    "ma_qfq_250": "ma250",
    "macd_dif_qfq": "macd",        # 保持原字段名（策略中会再 rename 为 macd_dif）
    "macd_dea_qfq": "macd_signal", # 保持原字段名（策略中会再 rename 为 macd_dea）
    "macd_qfq": "macd_hist",       # API 的 macd 实际是柱状图
    "kdj_k_qfq": "kdj_k",
    "kdj_d_qfq": "kdj_d",
    "kdj_qfq": "kdj_j",
    "boll_upper_qfq": "boll_upper",
    "boll_mid_qfq": "boll_middle",
    "boll_lower_qfq": "boll_lower",
    "rsi_qfq_6": "rsi6",
    "rsi_qfq_12": "rsi12",
    "rsi_qfq_24": "rsi24",
    "atr_qfq": "atr",
    "cci_qfq": "cci",
    "wr_qfq": "wr",
    "wr1_qfq": "wr1",
    "close_qfq": "close_qfq",
}
```

#### 4.1.4 废弃的脚本（可删除或标记废弃）

| 脚本 | 说明 |
|------|------|
| `backend/scripts/one_time/calculate_indicators.py` | 全量计算指标（被 API 替代） |
| `backend/scripts/daily/calculate_indicators_append.py` | 增量追加指标（被 API 替代） |
| `backend/scripts/daily/calculate_indicators_incremental.py` | 增量计算指标（被 API 替代） |

**处理方式**：直接删除，无需过渡期。

---

### 4.2 存储改动

#### 4.2.1 Parquet 分区结构（保持不变）

```
data/features/indicators/ts_code={ts_code}/year={year}/part-*.parquet
```

结构不变，字段集合变化：
- 移除：`ma120`, `ma200`, `ma500`, `rsi`
- 新增：`ma90`, `rsi6`, `rsi12`, `rsi24`, `atr`, `cci`, `wr`, `wr1`, `updays`, `downdays`, `pe`, `pe_ttm`, `pb`, `turnover_rate`, `turnover_rate_f`, `volume_ratio`, `close_qfq`

#### 4.2.2 DuckDB 查询层（无需改动）

`list_indicators()` 使用 `SELECT *`，字段变化会自动反映，无需改代码。

---

### 4.3 策略代码改动

#### 4.3.1 RSI 字段变更

现有策略使用 `rsi`（RSI(14)），API 不提供 RSI(14)，需改用 `rsi12`（RSI(12)，最接近）。

**需改动的文件**：

| 文件 | 现有字段 | 改为 |
|------|---------|------|
| `backend/scripts/strategy/second.py` (EarlyBreakoutSignalModel) | `rsi` | `rsi12` |
| `backend/scripts/strategy/third.py` (DailySignalModel) | `rsi` | `rsi12` |

**改动示例**（`second.py`）：
```python
# 改前
df["rsi"] = indicators["rsi"]
# 改后
df["rsi"] = indicators["rsi12"]
```

#### 4.3.2 base_strategy.py 重命名逻辑

`base_strategy.py` 当前将 `macd` → `macd_dif`、`macd_signal` → `macd_dea`。
新方案保持相同的内部字段名（`macd` 和 `macd_signal`），所以 **base_strategy.py 的重命名逻辑不需要改动**。

#### 4.3.3 MaCrossSignalModel（first.py）

使用 `ma5` 和 `ma20`，这两个字段在新方案中保持不变。**无需改动**。

---

### 4.4 API 改动

#### 4.4.1 `/api/stocks/{ts_code}/features` 端点

**无需代码改动**。该端点返回 `list_indicators(ts_code)` 的全部字段，字段变化会自动反映。

#### 4.4.2 可选：新增字段文档

如果前端需要知道有哪些可用字段，可以新增一个端点：
```
GET /api/stocks/indicator-fields
```
返回所有可用指标字段的列表和描述。（可选，非必须）

---

### 4.5 前端改动

#### 4.5.1 K 线图页面（`frontend/pages/stocks/[ts_code].js`）

**已在使用的字段**：

| 图表位置 | 字段 | 改动 |
|---------|------|------|
| 主图 MA | `ma5`, `ma10`, `ma20`, `ma30` | 无需改动 |
| KDJ 子图 | `kdj_k`, `kdj_d`, `kdj_j` | 无需改动 |
| MACD 子图 | `macd`, `macd_signal`, `macd_hist` | 无需改动 |

**当前不展示但可选新增的图表**：

| 图表 | 字段 | 说明 |
|------|------|------|
| RSI 子图 | `rsi6`, `rsi12`, `rsi24` | 可新增 RSI 子图，展示三条线 |
| BOLL 主图叠加 | `boll_upper`, `boll_middle`, `boll_lower` | 可叠加到 K 线主图 |
| ATR 子图 | `atr` | 波动率参考 |
| 估值信息 | `pe`, `pe_ttm`, `pb` | 可在侧栏或 tooltip 展示 |
| 量比 | `volume_ratio` | 可在成交量子图展示 |

**建议**：本次重构只做字段替换，新增图表作为后续优化。

#### 4.5.2 样式调整

无需改动。

---

### 4.6 daily.sh 改动

#### 4.6.1 替换计算指标任务

```bash
# 改前
run_task "计算每日指标" "python backend/scripts/one_time/calculate_indicators.py"

# 改后
run_task "同步每日技术因子" "python backend/scripts/daily/sync_stk_factor_pro.py --last-days 1"
```

#### 4.6.2 调度顺序

同步技术因子依赖日线数据已拉取，但不依赖本地计算，因此可以和拉取日线并行或紧随其后：

```
1) pull_daily_history     → 拉取日线
2) sync_stk_factor_pro    → 同步技术因子（替代 calculate_indicators）
3) calculate_signal        → 计算信号（依赖 1 和 2）
4) sync_shenwan_members    → 同步成分股
5) sync_shenwan_daily      → 同步板块行情
```

---

## 5. 数据迁移方案

### 5.1 历史数据处理

需要拉取历史技术因子数据替换现有 Parquet 文件。

**方案**：
```bash
# 1. 备份现有指标数据
cp -r data/features/indicators data/features/indicators_backup

# 2. 清空现有指标目录
rm -rf data/features/indicators/*

# 3. 按日期范围拉取历史数据（从数据起始日到今天）
python backend/scripts/daily/sync_stk_factor_pro.py --start-date 20200101 --end-date 20260206

# 4. 验证数据完整性后删除备份
rm -rf data/features/indicators_backup
```

**耗时估算**：
- 每个交易日 = 1 次 API 调用，返回约 5000 条（远低于 10000 上限）
- 6 年（2020–2026）约 1500 个交易日 = 1500 次调用
- 每分钟 30 次，即每 2 秒 1 次 → 1500 × 2 秒 ≈ 50 分钟
- 拉取前查 `trade_calendar`，自动跳过非交易日

### 5.2 新旧数据兼容

过渡期间可能存在：
- 旧数据有 `rsi` 字段，新数据有 `rsi12` 字段
- 策略代码需先改好字段名再切换数据

**建议执行顺序**：
1. 先部署策略代码改动（`rsi` → `rsi12`）
2. 再替换数据
3. 验证策略运行正常

---

## 6. 开发检查清单

### 阶段 1: 后端数据层
- [ ] `backend/app/data/tushare_client.py` 新增 `fetch_stk_factor_pro()` 函数
- [ ] 新增 `backend/scripts/daily/sync_stk_factor_pro.py` 同步脚本
  - [ ] 支持 --trade-date, --last-days, --start-date, --end-date
  - [ ] 查 trade_calendar 跳过非交易日
  - [ ] 字段选择与重命名
  - [ ] 写入 Parquet（沿用分区结构）

### 阶段 2: 策略代码适配
- [ ] `backend/scripts/strategy/second.py`：`rsi` → `rsi12`
- [ ] `backend/scripts/strategy/third.py`：`rsi` → `rsi12`
- [ ] `backend/scripts/strategy/base_strategy.py`：确认无需改动

### 阶段 3: daily.sh 更新
- [ ] 替换 `calculate_indicators` 为 `sync_stk_factor_pro`

### 阶段 4: 数据迁移
- [ ] 备份现有指标数据
- [ ] 拉取历史技术因子数据
- [ ] 验证数据完整性
- [ ] 验证策略运行正常

### 阶段 5: 清理
- [ ] 删除废弃脚本
  - [ ] `backend/scripts/one_time/calculate_indicators.py`
  - [ ] `backend/scripts/daily/calculate_indicators_append.py`
  - [ ] `backend/scripts/daily/calculate_indicators_incremental.py`
- [ ] 更新 DAILY_TASK.md
- [ ] 更新 AGENTS.md / CLAUDE.md 中的相关说明

---

## 7. 风险与注意事项

### 7.1 API 限制
- 5000 积分：每分钟 30 次请求（按 `trade_date` 调用，1 天 = 1 次，绑定足够）
- 单次最大 10000 条数据（按日拉取约 5000 条，无需分页）
- 每日增量同步仅需 1 次调用，无频率瓶颈

### 7.2 字段差异
- **RSI 参数不同**：自算 RSI(14)，API 提供 RSI(6/12/24)
- **MA 周期不同**：自算有 MA120/200/500，API 提供 MA90/250
- **MACD 字段命名**：API 的 `macd` 实际是柱状图，需注意映射

### 7.3 数据质量
- API 数据由 TuShare 社区维护，可能与自算结果有微小差异（浮点精度、算法实现）
- 策略信号可能因指标微调而略有变化
- 建议对比新旧数据，确认差异在可接受范围内

### 7.4 向后兼容
- 前端字段名保持不变（通过重命名），无需前端改动
- 策略代码只需改 RSI 字段名
- API 层无需改动
