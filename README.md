# 股票量化分析与回测工具需求说明

面向日级别 A 股数据的量化研究工具，提供数据拉取、指标计算、策略加载、交易信号生成及回测能力。设计目标：可扩展、可维护、方便集成多种策略与数据源。

## 1. 系统架构

* **数据层**：统一的数据接口，支持多数据源（券商/第三方行情 API、本地 CSV/Parquet）。数据标准化后存储到本地数据库或文件（推荐 Parquet + DuckDB/SQLite）。
* **计算层**：指标计算与特征工程。针对日线数据计算价格类、成交类和技术指标（MACD、KDJ 等），支持增量计算与缓存。
* **策略层**：策略插件化加载。每个策略暴露 `prepare`（预处理）、`generate_signals`（信号生成）、`on_backtest_end`（可选）接口。
* **执行层**：信号查询、单只股票回测和绩效分析。支持指定日期+股票的信号获取，以及单标的日级回测。
* **接口层**：CLI/HTTP 服务（可选）统一入口，提供数据刷新、指标重算、策略回测等命令。

## 2. 数据需求

### 2.1 拉取范围

* **标的**：全部 A 股（含主板/科创板/创业板/北交所）。需要基本信息（代码、名称、上市/停牌状态、行业）与日线行情。
* **频率**：每日收盘后执行拉取任务（可用定时器/cron）。

### 2.2 行情字段（最小集合）

| 字段 | 说明 |
| --- | --- |
| trade_date | 交易日期（yyyy-MM-dd） |
| ts_code / symbol | 交易代码，统一编码 |
| open / high / low / close | 当日开高低收 |
| pre_close | 前收 |
| pct_chg | 涨跌幅（%） |
| vol | 成交量（手或股，需注明单位） |
| amount | 成交额（元） |
| turnover_rate（可选） | 换手率 |

### 2.3 技术指标

如 API 不直接提供，则在计算层生成：

* **MACD**：DIF、DEA、MACD（12, 26, 9 默认）。
* **KDJ**：K、D、J（默认 9, 3, 3）。
* **MA/EMA**：常用 5/10/20/30/60。
* **ATR**（可选）：波动率度量。
* **RSI**（可选）：强弱指标。

要求：指标计算应可配置参数、可扩展（新增指标只需实现统一接口），支持按日期增量更新，避免全量重算。

### 2.4 数据存储与一致性

* 数据表/文件分区：按市场或年份分区，字段包含主键（ts_code, trade_date）。
* 校验：拉取后执行数据完整性检查（交易日缺失、停牌日过滤、量价为 0 的异常行等）。
* 版本化（可选）：保留原始行情与修正/前复权行情，记录数据源与拉取时间。

## 3. 策略框架

### 3.1 策略接口

策略作为模块化插件，约定统一接口：

```python
class Strategy:
    name: str
    params: dict

    def prepare(self, data_api):  # 可选
        """执行策略所需的缓存/预处理（如加载行业、财报因子）。"""

    def generate_signals(self, df):  # 必需
        """
        输入：单只股票的日线 DataFrame（含指标）。
        输出：DataFrame/Series，index 为 trade_date，值为 {buy, sell, hold} 或数值信号。
        """

    def on_backtest_end(self, report):  # 可选
        """回测结束时的收尾动作（记录日志、导出图表等）。"""
```

策略配置文件示例（YAML/JSON）：

```yaml
strategy: macd_cross
params:
  fast: 12
  slow: 26
  signal: 9
```

### 3.2 信号标准

* 统一信号枚举：`BUY` / `SELL` / `HOLD`（或 `NO_ACTION`）。可扩展为带打分的数值信号。
* 优先级：同日多信号时定义优先规则（如 SELL > BUY > HOLD），并在回测中保持一致。

## 4. 功能点

1. **数据刷新**：每日收盘后拉取最新日线与基本信息，落库并计算缺失指标。
2. **指标重算**：针对历史数据（或指定日期区间）重新计算指标，支持增量。
3. **策略管理**：列出策略、加载策略、更新策略配置。
4. **信号查询**：输入（策略、日期、股票），返回单日信号（买入/卖出/不操作）。
5. **单标的回测**：输入（策略、起止日期、股票），输出绩效报表与曲线。

## 5. 回测设计（单只股票）

### 5.1 基础设定

* 价格执行：默认用日线收盘价成交，可配置 T+1 开盘价成交。
* 成交与滑点：可配置固定滑点（如 1bp）和手续费（双边/单边费率）。
* 仓位规则：全仓/半仓/固定仓位百分比，可在策略层输出目标仓位。
* 复权处理：默认前复权数据进行回测，保持连续性。

### 5.2 绩效指标

* 年化收益、累计收益、最大回撤、夏普比率、卡玛比率、胜率、平均盈亏比。
* 交易统计：交易次数、平均持仓天数、换手率、最大单笔亏损。
* 可选：基准对比（沪深 300/中证 500）、月度/年度分布。

### 5.3 输出

* 回测明细：逐日净值、仓位、信号、成交价格、持仓成本。
* 汇总报表：核心指标表、收益曲线、回撤曲线（可导出 CSV/PNG）。

## 6. 组件与模块划分

| 模块 | 主要职责 |
| --- | --- |
| `data_provider` | 对接数据源，拉取与校验行情、基本面、复权因子 |
| `storage` | 数据落地与查询（DuckDB/SQLite/Parquet），主键与索引管理 |
| `indicators` | 指标计算库，统一接口与参数化配置 |
| `strategies` | 策略插件目录，基类 + 策略注册与加载 |
| `signals` | 信号标准化、冲突消解、信号查询接口 |
| `backtester` | 单标的回测引擎，执行规则、费用、滑点、统计指标 |
| `cli` / `api` | 命令行或 HTTP 服务：数据刷新、策略回测、信号查询 |

## 7. 运行与调度

* **调度**：使用 cron/systemd/任务队列，每日收盘后执行数据刷新与指标增量计算。
* **缓存**：指标计算结果与回测结果可做文件缓存，避免重复计算。
* **日志与监控**：统一日志格式，记录数据拉取失败、缺口补齐、策略异常。

## 8. 配置与可扩展性

* 配置文件（YAML/JSON）：数据源凭据、拉取时间、指标参数、费用与滑点、基准指数、回测日期范围。
* 插件扩展：新增数据源、指标、策略只需在对应目录注册，不影响核心框架。
* 环境隔离：支持在虚拟环境/容器中运行，依赖管理（pandas、ta-lib 或自实现指标库）。

## 9. 安全与合规

* 数据源凭据需通过环境变量或密钥管理存储。
* 若提供 HTTP API，需加认证与访问控制。

## 10. 开发里程碑（建议）

1. 完成数据模块：拉取日线行情 + 基本信息，落地存储并增量更新。
2. 完成指标模块：MACD、KDJ、MA/EMA，支持参数化与增量计算。
3. 策略接口与样例策略：实现 MACD 交叉、KDJ 共振等示例策略。
4. 信号查询 CLI：`signal --strategy macd --date 2024-01-10 --code 600000.SH`。
5. 单标的回测引擎：收盘/开盘成交模式、手续费与滑点、绩效输出。
6. 报表与可视化：收益/回撤曲线、交易明细导出。

## 11. 数据模块实现（当前完成）

* 提供了数据层的最小实现，包括：
  * **Provider 接口**：`BaseDataProvider` 约定 `fetch_basic_info` 与 `fetch_daily_bars`。
  * **存储层**：`SQLiteStorage`（示例）与 **`DuckDBStorage`（列式/Parquet 导出）**。
  * **数据编排**：`DailyIngestor` 负责从 provider 拉取、校验并写入存储。
* 默认的 `InMemoryProvider` 便于单元测试和离线演示，实际对接行情 API 时可自定义 provider。

### 11.0 数据源 / API 选项与可获取范围

> 当前仓库未内置任何外部行情 API 凭据或实现，只提供 `BaseDataProvider` 接口；需要按实际数据源自行扩展。

常见可选方案（需自行申请密钥/授权，注意合规与频控）：

* **TuShare Pro**：全市场 A 股基础信息、日线/复权行情，可获取历史数据（适配 `pro_bar` 等接口）。
* **聚宽 JQData**：付费数据，覆盖全历史 A 股基础信息与日线/复权行情。
* **Akshare**：开源数据聚合，可拉取部分全市场历史数据；需自行校验质量与稳定性。
* **其他数据商/券商 API**：如 Wind/同花顺/腾讯行情等，可按需编写 adapter。

接入步骤（保持与现有架构兼容）：

1. 按数据源文档获取基础信息与日线行情，规范字段以构造 `BasicInfo`、`DailyBar`。
2. 在 `freedom.data.provider` 下新增 provider（例如 `TushareProvider`），实现 `fetch_basic_info` 与 `fetch_daily_bars`。
3. 继续使用 `DailyIngestor` 落库；若数据量大或需要高吞吐，可替换存储为 DuckDB/Parquet、ClickHouse、PostgreSQL/TimescaleDB 等。

### 11.1 TuShare + DuckDB 示例（推荐生产使用列式存储）

```python
import os
from datetime import date
from freedom.data.ingestor import DailyIngestor
from freedom.data.provider import TushareProvider
from freedom.data.storage_duckdb import DuckDBStorage

os.environ["TUSHARE_TOKEN"] = "<your-tushare-token>"

provider = TushareProvider()  # 默认从环境变量读取 token
storage = DuckDBStorage("data/data.duckdb", "data/parquet")
ingestor = DailyIngestor(provider, storage)

# 拉取指定交易日的数据
result = ingestor.ingest(date(2024, 1, 10))
print(result)

# 导出 Parquet，便于回测/指标计算
storage.export_parquet()
```

> TuShare 有频控，请按交易日/年度分片批量拉取并做好重试；全历史回填时推荐列式存储（DuckDB/Parquet）。

### 11.2 使用示例（本地演示/SQLite）

```python
from datetime import date
from freedom.data.ingestor import DailyIngestor
from freedom.data.provider import InMemoryProvider
from freedom.data.storage import SQLiteStorage
from freedom.data.models import BasicInfo, DailyBar

basic = [BasicInfo(ts_code="600000.SH", name="PF Bank", market="SH", list_date=date(1999, 11, 10))]
bars = [
    DailyBar(
        ts_code="600000.SH",
        trade_date=date(2024, 1, 10),
        open=10.0, high=10.5, low=9.8, close=10.2,
        pre_close=9.9, pct_chg=3.03, vol=1200000, amount=12500000.5, turnover_rate=1.2,
    ),
]

provider = InMemoryProvider(basic_infos=basic, daily_bars=bars)
storage = SQLiteStorage("data/data.db")
ingestor = DailyIngestor(provider, storage)

result = ingestor.ingest(date(2024, 1, 10))
print(result)  # {'basic_info': 1, 'daily_bars': 1}
```

### 11.3 本地运行测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```
