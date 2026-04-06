# 每日信号系统设计：从回测到实盘

## 1. 目标

基于现有策略版本化管理 + `multifactor_v1` 回测引擎，构建**从回测验证到实盘辅助**的完整信号链路，支持两种并行模式：

1. **模拟盘（替代当前 Daily Signal 页面）**：用虚拟账户按信号自动模拟执行，验证策略样本外表现，零用户操作。
2. **实盘跟踪**：用户每日录入真实持仓和操作，系统根据真实持仓生成次日买卖建议，信号完全贴合实盘。
3. 统一信号引擎：两种模式共享同一套 `StrategySignalService`，区别仅在于持仓数据来源不同。
4. 信号推送：将每日买卖信号推送给用户，辅助交易决策。

**两种模式对比：**

| | 模拟盘（替代 Daily Signal） | 实盘跟踪 |
|------|------|------|
| 持仓来源 | 系统虚拟组合，自动更新 | 用户手动录入的真实持仓 |
| 卖出信号 | 基于虚拟持仓，可能与实际不同 | 基于真实持有，完全贴合 |
| 买入信号 | 基于虚拟现金余额 | 基于真实可用资金 |
| 用户操作 | 零操作，纯看 | 每天录入 1 次 |
| 准确度 | 可能偏离 | 精准 |
| 核心价值 | 样本外验证策略有效性 | 实盘辅助决策，精准匹配真实仓位 |
| 典型场景 | 策略刚通过回测，需要验证 | 已确认策略有效，正式投入实盘 |

> **为什么需要两种模式？** 模拟盘像"纸上谈兵"，系统自动运行虚拟账户，验证策略在真实行情下的表现。但实际操作中，用户可能没有完全按信号执行（资金不足、涨停买不到、个人判断调整等），导致真实持仓与虚拟持仓产生偏差。实盘跟踪解决这个问题——系统知道你真正持有什么，才能精准告诉你"你手上的 XX 该卖了"。

本文是产品与系统设计文档，不包含代码实现。

---

## 2. 当前平台现状

### 2.1 已具备的能力

| 模块 | 说明 |
|------|------|
| 策略定义 + 版本管理 | `strategy_definitions` + `strategy_versions`，含完整 `params_snapshot` |
| 多因子回测引擎 | `multifactor_v1`：市场状态分类、多因子打分（趋势35% + 板块25% + 价值25% + 流动性15%）、止损/止盈、仓位轮动 |
| 回测结果可视化 | 净值曲线、交易记录、持仓快照、KPI 指标（累计收益、最大回撤、夏普比率等） |
| 每日数据拉取 | 通过 `daily.sh`（当前手动）或 scheduler（恢复后）拉日线行情 + `stk_factor_pro` 因子数据 |
| 参数版本化 | `params_snapshot` 记录策略完整参数快照，可精确复现任意版本 |

### 2.2 关键缺口

| 缺口 | 说明 |
|------|------|
| 无"每日信号生成"能力 | 回测引擎仅支持历史回放模式，无法以"单日计算"模式复用 |
| 信号计算未自动化 | scheduler 只跑数据拉取，无每日信号计算任务 |
| 无"策略激活"概念 | 没有从"回测验证通过"到"每日产出交易信号"的状态流转 |
| 无模拟盘能力 | 无法用真实行情验证策略在样本外的表现 |
| 无通知/提醒机制 | 信号产出后没有推送能力 |
| 无交易执行辅助 | 没有委托单生成、风控检查等功能 |

### 2.3 废弃说明

旧的 `EarlyBreakoutSignalModel`、`DailySignalModel` 不再使用。所有信号生成统一基于回测引擎的 `multifactor_v1` 策略。

旧的 `daily-signals.js` 页面保留并改名为 **Daily Signals(旧)**。新架构新增 **Daily Signals** 页面，统一读取 `strategy_signals_daily`，与旧页面并行存在，待你确认后再下线旧页。

### 2.4 当前用户操作流程与断点

当前用户在策略中心（`strategies.js`）的操作路径：

```
策略中心页 (/strategies)
  │
  ├─ 1. 点击策略表格行 → 选中一个策略（selectedStrategyId）
  ├─ 2. "发布版本"表单：填写 params_snapshot (JSON) + code_ref + 变更说明 → POST /strategies/{id}/versions
  ├─ 3. "创建回测Run"表单：选择版本(下拉框) + 日期区间 → POST /backtests → 跳转到回测详情页
  └─ 4. 回测详情页 (/backtests/[run_id])：查看 KPI（累计收益、最大回撤、夏普比率等）
       │
       └─ ❌ 断点：看到效果好的版本，无任何操作可以"激活"它
```

**断点分析 — 缺失的 3 个环节：**

| # | 缺失环节 | 说明 |
|---|---------|------|
| 1 | 版本无能力位字段 | `strategy_versions` 只存 `params_snapshot`/`code_ref`/`change_log`，无法表达 `paper_enabled` / `live_tracking_enabled` / `push_enabled` 的并行状态 |
| 2 | 无"激活"操作入口 | 回测详情页只有 KPI 展示和"返回"按钮，没有"启动模拟盘"或"激活信号"的按钮；策略中心的版本也仅在下拉框中展示，无操作列 |
| 3 | 无后端每日运行机制 | 即使前端有了激活按钮，后端 scheduler 也没有"查找所有激活版本 → 逐个计算今日信号"的任务 |

### 2.5 最小功能闭环

要实现"选定版本 → 生成每日信号"的完整链路，需要补齐以下步骤：

| 步骤 | 用户动作 | 对应功能 | 现状 |
|------|---------|---------|------|
| 1 | 创建策略 + 发布版本 | 策略中心表单 | ✅ 已有 |
| 2 | 选择版本，创建回测 Run | 创建回测表单 | ✅ 已有 |
| 3 | 查看回测效果，确认满意 | 回测详情页 KPI | ✅ 已有 |
| 4 | 点击"启动模拟盘" | `POST /api/paper-portfolios` | ❌ 需新增 |
| 5 | 系统每日计算信号 | nightly 手动脚本 + `StrategySignalService` | ❌ 需新增 |
| 6 | 查看每日信号 + 模拟盘表现 | 模拟盘详情页 / 今日信号页 | ❌ 需新增 |
| 7 | 确认样本外有效，开启推送 | "开启信号推送"按钮 | ❌ 需新增（P1） |

---

## 3. 策略生命周期模型

将策略从研发到实盘分为多个阶段，其中模拟盘验证后可**并行**进入实盘跟踪和信号推送：

```
研发 → 回测 → 模拟盘 ─┬→ 实盘跟踪（用户录入真实持仓，精准建议）
 ①      ②       ③     ├→ 信号推送（当前手动触发）
                       └→ 交易执行辅助（远期）
```

> **关键区分：** 模拟盘（③）是样本外验证环节，系统用虚拟账户自动运行。实盘跟踪是**独立并行**的模块，用户录入真实持仓后系统基于真实持仓生成建议。两者可同时运行、互不干扰。

### 阶段① 研发（已有）

- 创建策略定义，调整参数，保存版本。
- 每个版本通过 `params_snapshot` 记录完整参数快照。

### 阶段② 回测验证（已有）

- 选定策略版本，跑历史回测，查看 KPI。
- **新增**：回测结果页增加"启动模拟盘"按钮，作为进入下一阶段的入口。
- 当回测 status == "success" 时，按钮可用；否则置灰。

### 阶段③ 模拟盘（核心新增）

这是回测到实盘的**核心桥梁**。

**产品逻辑：**
- 用户对某个回测效果好的策略版本点击"启动模拟盘"。
- 系统每日收盘后，用**回测引擎的同一套代码**（`BacktestEngine`），以 T 日真实行情运行该策略版本的 `params_snapshot`。
- 产出当日的买入信号、卖出信号、目标持仓。
- 同时维护一个虚拟账户，按信号模拟执行，跟踪净值曲线。
- 用户可在前端看到：模拟盘净值 vs 基准、每日信号、持仓变化。

**激活入口设计：**

入口位于**回测详情页**（`/backtests/[run_id]`），在 KPI 区域旁增加操作按钮：

```
回测详情页 (/backtests/[run_id])
┌──────────────────────────────────────────────┐
│ KPI 区域（累计收益、最大回撤、夏普比率...）        │
├──────────────────────────────────────────────┤
│ [启动模拟盘]  [返回回测列表]                     │
│                                              │
│ 点击"启动模拟盘"后弹出确认弹窗：                  │
│ ┌────────────────────────────┐               │
│ │ 启动模拟盘                   │               │
│ │                            │               │
│ │ 策略版本: v3 (abc123)       │               │
│ │ 初始资金: [1,000,000]       │               │
│ │ 起始日期: [2025-02-10]      │               │
│ │                            │               │
│ │ [取消]  [确认启动]           │               │
│ └────────────────────────────┘               │
└──────────────────────────────────────────────┘
```

确认后调用：
```
POST /api/paper-portfolios
{
  "strategy_version_id": "从 backtest_run 中获取",
  "initial_capital": 1000000,
  "start_date": "20250210"
}
```

后端处理：
1. 在 `strategy_portfolios` 创建一条 `portfolio_type=paper` 记录
2. 将对应 `strategy_versions.paper_enabled` 更新为 `true`
3. 返回 `portfolio_id`，前端跳转到 `/paper-trading/{portfolio_id}`

**约束规则：**
- 同一个 `strategy_version_id` 只能有一个 running 状态的模拟盘（防止重复激活）
- 如果该版本已有模拟盘在运行，按钮文案变为"查看模拟盘"，点击跳转到对应详情页
- 停止模拟盘后，`strategy_versions.paper_enabled=false`，可重新启动

**为什么不能跳过模拟盘？**
- 回测存在过拟合风险，模拟盘是样本外验证。
- 给用户建立信心的缓冲期（建议至少跑 20-60 个交易日）。
- 对比模拟盘表现与回测预期是否一致，发现策略退化。

### 阶段④ 信号推送（能力位开启）

**产品逻辑：**
- 模拟盘运行一段时间后，用户确认策略有效，开启 `push_enabled`。
- 每日产出的信号推送给用户作为交易参考。
- 信号展示：今日买入推荐（股票、分数、理由）+ 今日卖出提醒（持仓中触发卖出条件的标的）。

**升级入口设计：**

入口位于**模拟盘详情页**（`/paper-trading/[id]`）：

```
模拟盘详情页 (/paper-trading/[id])
┌──────────────────────────────────────────────┐
│ 模拟盘 KPI（累计收益、最大回撤、运行天数...）      │
├──────────────────────────────────────────────┤
│ 运行天数 ≥ 20 个交易日时，按钮可用：              │
│ [开启信号推送]  [暂停模拟盘]  [停止模拟盘]        │
└──────────────────────────────────────────────┘
```

确认后调用：
```
POST /api/paper-portfolios/{id}/enable-push
{
  "notification_channels": ["webhook"],
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/..."
}
```

后端处理：
1. 将 `strategy_versions.push_enabled` 更新为 `true`
2. 模拟盘继续运行（同时跟踪模拟净值 + 推送信号）
3. 保存通知配置

**约束规则：**
- 运行天数 < 20 个交易日时，"开启信号推送"按钮置灰，tooltip 提示"建议至少运行 20 个交易日"
- 可通过 `POST /api/paper-portfolios/{id}/disable-push` 关闭推送，模拟盘继续运行

### 阶段⑤ 实盘跟踪（并行分支，核心新增）

> 实盘跟踪是**独立于模拟盘的并行分支**，不是模拟盘的"下一阶段"。用户可以在模拟盘验证的同时，或者验证通过后，创建实盘跟踪组合。

**产品逻辑：**
- 用户对某个策略版本创建"实盘跟踪"组合，录入真实的初始持仓和资金。
- 每天收盘后录入当日实际操作（买/卖）或直接同步持仓。
- 系统根据**真实持仓**（而非虚拟持仓）+ T 日行情，运行策略生成 T+1 建议。
- 建议精准匹配用户真实仓位：该卖的正好是用户持有的，买入建议基于真实可用资金。

**与模拟盘的关系：**
- 模拟盘可以不开启实盘跟踪（纯验证阶段）
- 实盘跟踪可以不依赖模拟盘（直接从回测验证后创建）
- 两者可以同时运行，互不干扰
- 最佳实践：先开模拟盘验证 → 确认有效后再开实盘跟踪

**详细设计见 Section 12（实盘跟踪设计）。**

### 阶段⑥ 交易执行辅助（远期）

- 生成委托单草稿（股票、方向、数量、价格区间）。
- 用户一键确认后通过券商 API 下单。
- 注意：A 股程序化交易有合规要求，建议以"辅助决策"定位，而非"自动交易"。

---

## 4. 核心架构：统一信号引擎

### 4.1 问题

当前 `BacktestEngine` 仅支持"给定日期区间，从头到尾回放"的模式，无法单独计算某一天的信号。

### 4.2 方案：StrategySignalService

将回测引擎的打分和信号生成逻辑抽取为可独立调用的服务：

```python
class StrategySignalService:
    def generate_daily_signals(
        self,
        strategy_version_id: str,   # 使用哪个策略版本的参数
        date: str,                   # 计算哪天的信号（YYYYMMDD）
        current_portfolio: dict      # 当前持仓（用于卖出判断）
    ) -> DailySignalResult:
        """
        返回:
        - buy_signals: 买入候选列表（股票、分数、建议仓位）
        - sell_signals: 卖出信号列表（股票、原因、建议动作）
        - market_regime: 当日市场状态分类
        - scores: 全市场打分排名
        """
```

**复用关系：**
- 回测引擎调用它做历史回放 ✓
- 模拟盘调用它做每日模拟 ✓
- 实盘跟踪调用它做每日推荐 ✓
- **同一套逻辑，回测即所得**

**`current_portfolio` 参数来源说明：**

| 调用场景 | `current_portfolio` 数据来源 | 说明 |
|------|------|------|
| 回测引擎 | 回测引擎内部维护的虚拟持仓 | 每日回放时自动更新 |
| 模拟盘 | `strategy_portfolio_positions_daily`（`portfolio_type=paper`）最新快照 | 系统自动维护，无需用户介入 |
| 实盘跟踪 | `strategy_portfolio_positions_daily`（`portfolio_type=live`）最新快照 | 用户录入真实持仓后，系统从该表读取 |

> 三种场景的区别**仅在于 `current_portfolio` 的数据来源不同**，信号计算逻辑完全一致。这确保了"回测看到的效果 = 模拟盘/实盘的行为"。

### 4.3 需复用的回测引擎方法

从 `BacktestEngine` 中抽取以下核心逻辑：

| 方法 | 职责 |
|------|------|
| `_classify_market()` | 大盘状态分类（bull / bear / neutral / volatile） |
| `_score_candidates()` | 全市场多因子打分 |
| `_generate_sell_signals()` | 基于持仓的卖出信号生成（止损、止盈、trailing stop、信号退出） |
| `_execute_orders()` | 模拟执行（模拟盘使用，实盘信号不需要） |

### 4.4 数据依赖

单日信号计算需要的数据：

| 数据 | 来源 | 说明 |
|------|------|------|
| T 日 OHLCV | `raw/daily` Parquet | 当日行情 |
| T 日 daily_basic | `raw/daily_basic` Parquet | PE、PB、换手率、市值 |
| T 日技术因子 | `features/indicators` Parquet | MA、MACD、KDJ、RSI、BOLL 等 |
| T 日板块行情 | `shenwan_daily` | 板块涨跌幅、排名 |
| T 日大盘指数 | `market_index_dailybasic` | 大盘状态判断 |
| 历史数据窗口 | 同上 | 部分因子计算需要回看 N 日 |

所有数据由 `daily.sh`/scheduler 产出，本方案默认以手动 nightly 运行为主。

---

## 5. 领域对象示例（非主存储）

本节仅描述接口层/页面层使用的聚合对象，**不作为 MongoDB 主存储结构**。  
唯一落库模型以 Section 15 为准。

### 5.1 `DailySignalSnapshot`（页面聚合对象）

用途：给 `Daily Signals` 页面按日期展示“买入/卖出分组”。

来源：由 `strategy_signals_daily`（单标的一行）按 `signal_date + strategy_version_id + portfolio_id` 聚合生成。

```json
{
  "signal_date": "20250210",
  "signal_trade_date": "20250211",
  "strategy_version_id": "alpha:v3",
  "portfolio_id": "paper-xxx",
  "market_regime": "neutral",
  "buy_signals": [
    { "ts_code": "600519.SH", "name": "贵州茅台", "score": 82.0, "suggested_weight": 0.10 }
  ],
  "sell_signals": [
    { "ts_code": "000001.SZ", "name": "平安银行", "reason": "trailing_stop" }
  ]
}
```

### 5.2 `PortfolioOverview`（页面概览对象）

用途：模拟盘/实盘详情页顶部 KPI 卡片。

来源：`strategy_portfolios` + `strategy_portfolio_nav_daily` + `strategy_portfolio_positions_daily` 聚合。

```json
{
  "portfolio_id": "paper-xxx",
  "portfolio_type": "paper",
  "status": "running",
  "current_nav": 1052300,
  "cash": 520000,
  "position_value": 532300,
  "last_signal_date": "20250210"
}
```

### 5.3 `StrategyVersionCapabilities`（版本能力对象）

用途：策略中心页面状态展示与按钮可用性判断。

来源：`strategy_versions` 扩展字段。

```json
{
  "strategy_version_id": "alpha:v3",
  "paper_enabled": true,
  "live_tracking_enabled": false,
  "push_enabled": true,
  "frozen": true
}
```

---

## 6. 运行任务链（当前手动触发）

当前基础数据任务（由你手动触发）：

```
18:00  pull_daily_history.py      # 拉日线行情
18:00  sync_stk_factor_pro.py     # 拉技术因子
```

新增信号任务（同样由你手动触发）：

```
generate_strategy_signals.py      # 生成策略/组合 signal_date=T 的信号，signal_trade_date=T+1
settle_strategy_orders.py         # 结算 signal_trade_date=T 的 pending 订单
refresh_strategy_portfolios.py    # 更新组合净值与持仓快照
push_strategy_notifications.py    # 推送信号并写发送状态
```

任务依赖关系：

```
pull_daily_history ──┐
sync_stk_factor_pro ─┼──→ generate_strategy_signals ─→ settle_strategy_orders ─→ refresh_strategy_portfolios ─→ push_strategy_notifications
sync_zhishu_data    ─┘
```

> **注意：** 当前不依赖 scheduler 自动触发，统一用手动命令执行。后续 scheduler 恢复后再把这条链路接回自动化。

---

## 7. 信号推送方式

按优先级排列：

| 优先级 | 渠道 | 说明 |
|--------|------|------|
| P0 | 平台内 Dashboard | 登录后首页展示"今日信号"卡片 |
| P1 | 飞书群机器人 Webhook | 支持多群并行推送，配置简单 |
| P2 | 邮件推送 | 备选 |
| P3 | 钉钉 Webhook | 备选 |

> 当前阶段：飞书推送默认手动触发（执行 `push_strategy_notifications.py`），不依赖 scheduler 自动发送。

推送内容模板：

```
📊 Freedom Quant 每日信号 (2025-02-10)
策略: 多因子V1 - 稳健版
市场状态: 震荡

🟢 买入信号 (3只):
  600519.SH 贵州茅台  得分:82  建议仓位:10%
  000858.SZ 五粮液    得分:78  建议仓位:8%
  601318.SH 中国平安  得分:75  建议仓位:8%

🔴 卖出信号 (1只):
  000001.SZ 平安银行  原因:跟踪止损触发

📈 模拟盘: 累计+5.23%  今日+0.32%
```

---

## 8. 新增 API 端点

### 8.1 模拟盘管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/paper-portfolios` | 创建模拟盘（从回测详情页触发） |
| `GET` | `/api/paper-portfolios` | 模拟盘列表（支持 status 过滤、分页） |
| `GET` | `/api/paper-portfolios/{id}` | 模拟盘详情（含当前持仓、累计净值） |
| `POST` | `/api/paper-portfolios/{id}/pause` | 暂停模拟盘 |
| `POST` | `/api/paper-portfolios/{id}/resume` | 恢复模拟盘 |
| `POST` | `/api/paper-portfolios/{id}/stop` | 停止模拟盘（`strategy_versions.paper_enabled=false`） |
| `POST` | `/api/paper-portfolios/{id}/enable-push` | 开启推送能力（`push_enabled=true`） |
| `POST` | `/api/paper-portfolios/{id}/disable-push` | 关闭推送能力（`push_enabled=false`） |

### 8.2 每日信号

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/strategy-signals` | 查询每日信号（按 `signal_date`、`strategy_version_id`、`portfolio_id` 过滤） |
| `GET` | `/api/strategy-signals/latest` | 获取最新一天的信号（首页 Dashboard 用） |

### 8.3 模拟盘历史数据

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/paper-portfolios/{id}/nav-daily` | 模拟盘每日净值序列（画净值曲线） |
| `GET` | `/api/paper-portfolios/{id}/trades` | 模拟盘交易记录 |
| `GET` | `/api/paper-portfolios/{id}/signals` | 模拟盘每日信号历史 |

### 8.4 现有 API 扩展

| 方法 | 路径 | 变更说明 |
|------|------|---------|
| `GET` | `/api/strategies/{id}/versions` | 返回值增加 `backtest_status` + `paper_enabled`、`live_tracking_enabled`、`push_enabled` 字段 |
| `GET` | `/api/backtests/{run_id}` | 返回值增加 `can_start_paper`（该版本是否可启动模拟盘）和 `paper_portfolio_id`（已有模拟盘时返回 ID） |

---

## 9. 前端页面规划

### 9.1 新增/改造页面

| 页面 | 路由 | 功能 |
|------|------|------|
| 策略详情页（改造） | `/strategies/[id]` | 增加版本列表，每个版本显示：回测 KPI 摘要、生命周期状态标签（草稿/已回测/模拟中/实盘）、操作按钮 |
| 模拟盘列表（新增） | `/paper-trading` | 所有运行中的模拟盘一览，净值曲线缩略图、今日收益、累计收益 |
| 模拟盘详情（新增） | `/paper-trading/[id]` | 类似回测详情页，但数据实时更新；增加"开启信号推送"按钮 |
| Daily Signals(旧)（保留8周） | `/daily-signals-legacy` | 保留旧逻辑，仅展示旧 `daily_signal` 数据，页面标题 `Daily Signals(旧)` + deprecated 提示 |
| Daily Signals（新增） | `/daily-signals-v2`（过渡）→ `/daily-signals`（正式） | 展示 `strategy_signals_daily`，按策略版本/组合筛选 |
| 实盘跟踪列表（新增） | `/live-trading` | 所有实盘组合一览，净值、持仓、今日建议状态 |
| 实盘跟踪详情（新增） | `/live-trading/[id]` | 净值曲线、当前持仓、今日建议、录入操作入口 |
| 飞书群配置（新增） | `/settings/feishu-groups` | 维护多个飞书群机器人 Webhook（启用/停用） |

### 9.2 侧边栏导航调整

```
首页
板块
板块排名
大盘指数
自选
───────────
策略              ← 策略列表 + 版本管理
回测              ← 回测记录
模拟盘            ← 新增入口
实盘跟踪          ← 新增入口
Daily Signals(旧) ← 旧信号页面（保留）
Daily Signals     ← 新信号页面
───────────
飞书群配置        ← 新增
用户管理          ← 仅管理员
```

### 9.3 策略中心改造：版本列表表格化

当前策略中心页（`strategies.js`）的版本只在一个 `<select>` 下拉框中展示，无法看到每个版本的状态和操作。需改造为表格：

```
策略中心 → 选中某策略后，下方展示版本表格：

┌─────────┬────────────┬──────────────────────────┬──────────────┬──────────────────────┐
│ 版本号   │ 变更说明    │ 回测状态/能力位            │ 最佳回测收益  │ 操作                  │
├─────────┼────────────┼──────────────────────────┼──────────────┼──────────────────────┤
│ v1      │ 初始版本    │ backtested               │ +12.3%      │ [查看回测]             │
│ v2      │ 调高止损    │ backtested + push_enabled│ +18.7%      │ [查看信号]             │
│ v3      │ 加入板块因子 │ backtested + paper_enabled│ +22.1%      │ [查看模拟盘]           │
│ v4      │ 降低换手    │ draft                    │ -           │ [创建回测]             │
└─────────┴────────────┴──────────────────────────┴──────────────┴──────────────────────┘
```

状态标签样式：
- `draft`：灰色
- `backtested`：蓝色
- `paper_enabled=true`：绿色脉冲点 + "模拟盘开启"
- `live_tracking_enabled=true`：蓝绿标签 + "实盘跟踪开启"
- `push_enabled=true`：橙色标签 + "推送开启"

### 9.4 关键交互流程

**流程 A：从回测到模拟盘**

```
策略中心 → 选中策略 → 选择版本 → 创建回测Run → 跳转回测详情页
  → 回测完成，查看 KPI，确认满意
  → 点击"启动模拟盘"按钮
  → 弹窗确认：初始资金、起始日期
  → POST /api/paper-portfolios
  → 策略版本 paper_enabled → true
  → 跳转到模拟盘详情页 (/paper-trading/{id})
```

**流程 B：从模拟盘到实盘信号**

```
模拟盘详情页 → 运行 ≥20 个交易日 → 查看样本外表现
  → "开启信号推送"按钮变为可用
  → 点击后弹窗：配置推送渠道（飞书群机器人 Webhook，可多群）
  → POST /api/paper-portfolios/{id}/enable-push
  → 策略版本 push_enabled → true
  → 手动执行 `push_strategy_notifications.py` 推送信号
```

**流程 C：从策略中心直达**

```
策略中心 → 版本表格 → 状态列显示"🟢模拟中"
  → 点击"查看模拟盘" → 跳转 /paper-trading/{id}
```

**流程 D：停止/重置**

```
模拟盘详情页 → 点击"停止模拟盘"
  → POST /api/paper-portfolios/{id}/stop
  → 策略版本 paper_enabled → false
  → 可在回测详情页重新启动新的模拟盘
```

**流程 E：创建实盘跟踪**

```
模拟盘详情页 / 回测详情页 → 确认策略有效
  → 点击"创建实盘跟踪"
  → 弹窗：初始资金、初始持仓（可选）
  → POST /api/live-portfolios
  → 跳转到实盘跟踪详情页 (/live-trading/{id})
  → 每日 15:00-18:00 录入当天操作
  → 手动 nightly 脚本生成次日建议
```

**流程 F：实盘跟踪每日操作**

```
实盘跟踪详情页 → 收盘后 → 点击"录入今日操作"
  → 弹窗：选择录入方式
    → 方式A"录入交易"：填写买卖记录（股票、方向、价格、数量）
    → 方式B"同步持仓"：直接填写当前持有的股票和数量
  → POST /api/live-portfolios/{id}/trades 或 /positions
  → 系统自动更新持仓快照
  → 等待手动 nightly 脚本生成次日建议
  → 次日 09:30 前查看建议
```

---

## 10. 实施优先级

| 阶段 | 任务 | 价值 | 工作量 |
|------|------|------|--------|
| **P0** | 统一信号引擎：从 `BacktestEngine` 抽取 `StrategySignalService` | 消除架构割裂，后续所有功能的基础 | 中 |
| **P0** | 策略版本增加能力位字段（`paper_enabled/live_tracking_enabled/push_enabled`） | 并行状态流转基础 | 小 |
| **P0** | 手动 nightly 脚本串联信号任务 | 先稳定产出，后续再切 scheduler 自动化 | 小 |
| **P1** | 模拟盘后端：`strategy_portfolios(portfolio_type=paper)` + 每日更新逻辑 | 回测到实盘的核心桥梁 | 中 |
| **P1** | 模拟盘前端：列表页 + 详情页 | 用户可视化模拟盘表现 | 中 |
| **P1** | 实盘跟踪后端：`strategy_portfolios(portfolio_type=live)` + 录入 API + 信号生成 | 精准贴合真实仓位的核心功能 | 中 |
| **P1** | 实盘跟踪前端：列表页 + 详情页 + 录入弹窗 | 实盘辅助的用户界面 | 中 |
| **P1** | 新增 Daily Signals 页面（对接 `strategy_signals_daily`） | 实盘辅助的前端入口 | 中 |
| **P2** | 实盘跟踪信号推送（与模拟盘共用推送通道） | 实盘建议的及时触达 | 小 |
| **P2** | 飞书多群 Webhook 推送 | 实用价值最高的通知方式 | 小 |
| **P2** | 策略详情页改版（版本列表 + 状态标签） | 产品体验完整性 | 小 |
| **P3** | 风控规则引擎（单股比例上限、行业集中度、回撤熔断） | 实盘安全保障 | 中 |
| **P3** | 券商 API 对接 | 全自动交易（需注意 A 股合规要求） | 大 |

---

## 11. 总结

平台已具备**策略 → 版本化 → 回测**的完整闭环。离实盘辅助最关键的两步是：

> 1. **让回测引擎的逻辑能以"每日运行"的方式复用**，产出当天的交易信号。
> 2. **支持基于真实持仓生成建议**，让信号精准贴合实盘。

核心改动是把 `BacktestEngine` 中的选股打分和信号生成从"历史回放模式"解耦为"单日计算模式"，然后围绕它构建模拟盘和实盘跟踪两条并行路径：

- **模拟盘**：零操作验证策略样本外表现，是从回测到实盘的信心桥梁。
- **实盘跟踪**：基于用户真实持仓生成精准建议，是辅助交易决策的核心工具。

不需要重写引擎，只需要做好**抽取和复用**。策略参数已有 `params_snapshot` 版本化设计，可直接服务于模拟盘和实盘跟踪场景。

---

## 12. 实盘跟踪设计

> 本章节是实盘跟踪模块的完整产品与系统设计，涵盖每日循环流程、数据模型、API 端点、前端页面和录入方式。

### 12.1 定位与目标

实盘跟踪解决的核心问题是：**模拟盘的虚拟持仓可能与用户真实持仓产生偏差**。

偏差来源：
- 用户资金不足，无法完全按信号买入
- 某些股票涨停/跌停，无法成交
- 用户基于个人判断跳过部分信号
- 实际成交价格与信号价格存在差异

实盘跟踪通过让用户录入真实持仓，确保系统"知道你真正持有什么"，从而产出完全贴合实际的买卖建议。

### 12.2 每日循环流程

```
T日 15:00    收盘
T日 15:00-18:00  用户在"实盘跟踪"页面录入今天的操作和持仓
                  ├─ 方式A：录入当天买卖交易记录
                  └─ 方式B：直接同步当前持仓快照
T日 18:00    daily.sh 拉取当日行情数据 + 技术因子
T日 18:22    手动触发 generate_strategy_signals.py，读取【真实持仓】+ T日行情 → 生成 T+1 建议
T+1日 09:15  用户登录查看系统生成的建议
T+1日 09:30  开盘，用户参考建议进行操作
T+1日 15:00  收盘，录入实际操作 ... 循环
```

**时间窗口说明：**
- 用户有 **3 小时**（15:00-18:00）的录入窗口
- 默认当日录入截止时间：`18:20`（Asia/Shanghai）
- 如果用户未录入，系统使用上一次的持仓快照生成建议（可能不准确，但不会中断）
- `18:20` 之后录入标记 `late_input=true`，按补录流程触发 `recompute_from_date`
- 建议在录入页面显示"上次录入时间"，提醒用户及时更新

### 12.3 接口对象（实盘页面）

#### `strategy_portfolios`（`portfolio_type=live`）

```json
{
  "_id": ObjectId,
  "portfolio_id": "uuid",
  "strategy_version_id": "版本ID",
  "strategy_name": "策略名",
  "status": "running | paused | stopped",
  "initial_capital": 1000000,
  "current_cash": 520000,
  "created_at": "2025-02-10T18:30:00",
  "last_input_date": "20250215",
  "last_signal_date": "20250215",
  "note": "实盘跟踪备注"
}
```

#### `strategy_portfolio_trades`（`source=manual_input`）

```json
{
  "_id": ObjectId,
  "portfolio_id": "组合ID",
  "trade_date": "20250215",
  "ts_code": "600519.SH",
  "stock_name": "贵州茅台",
  "side": "BUY",
  "price": 1680.50,
  "qty": 100,
  "amount": 168050.00,
  "fee": 50.42,
  "input_at": "2025-02-15T16:30:00",
  "note": "按建议买入"
}
```

#### `live_positions_snapshot`（接口聚合视图，不单独建表）

由 `strategy_portfolio_positions_daily`（`portfolio_type=live`）按 `portfolio_id + trade_date` 聚合生成：

```json
{
  "_id": ObjectId,
  "portfolio_id": "组合ID",
  "trade_date": "20250215",
  "positions": [
    {
      "ts_code": "600519.SH",
      "stock_name": "贵州茅台",
      "shares": 100,
      "cost_price": 1680.50,
      "market_value": 168800.00
    },
    {
      "ts_code": "000858.SZ",
      "stock_name": "五粮液",
      "shares": 500,
      "cost_price": 152.30,
      "market_value": 78500.00
    }
  ],
  "total_position_value": 247300.00,
  "cash": 520000.00,
  "total_asset": 767300.00,
  "source": "trade_derived | manual_sync",
  "input_at": "2025-02-15T16:35:00"
}
```

> **`source` 字段说明：**
> - `trade_derived`：由录入的交易记录自动推演得出
> - `manual_sync`：用户直接编辑/同步的持仓快照

#### `live_signals_daily`（接口聚合视图，不单独建表）

由 `strategy_signals_daily` 按 `portfolio_type=live` 聚合生成：

```json
{
  "_id": ObjectId,
  "strategy_version_id": "版本ID",
  "portfolio_id": "实盘组合ID",
  "portfolio_type": "live",
  "signal_date": "20250215",
  "signal_trade_date": "20250217",
  "market_regime": "neutral",
  "buy_signals": [
    {
      "ts_code": "601318.SH",
      "name": "中国平安",
      "score": 78.0,
      "factors": { "trend": 82.0, "sector": 75.0, "value": 80.0, "liquidity": 85.0 },
      "suggested_weight": 0.08,
      "suggested_amount": 61384.00
    }
  ],
  "sell_signals": [
    {
      "ts_code": "000858.SZ",
      "name": "五粮液",
      "reason": "trailing_stop",
      "detail": "从高点回撤超过5%",
      "current_shares": 500,
      "suggested_action": "全部卖出"
    }
  ],
  "generated_at": "2025-02-15T18:22:00"
}
```

> 说明：`strategy_signals_daily` 为单标的一行主表；`live_signals_daily` 仅是接口响应形态，便于前端按天展示。

### 12.4 API 端点

#### 实盘组合管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/live-portfolios` | 创建实盘组合（指定策略版本、初始资金） |
| `GET` | `/api/live-portfolios` | 实盘组合列表（支持 status 过滤、分页） |
| `GET` | `/api/live-portfolios/{id}` | 实盘组合详情（含当前持仓、最新净值、今日建议） |
| `POST` | `/api/live-portfolios/{id}/stop` | 停止跟踪 |

#### 交易录入

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/live-portfolios/{id}/trades` | 录入当日交易操作（买/卖记录） |
| `GET` | `/api/live-portfolios/{id}/trades` | 交易历史（支持日期范围过滤、分页） |
| `DELETE` | `/api/live-portfolios/{id}/trades/{trade_id}` | 删除错误的交易记录 |

#### 持仓管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/live-portfolios/{id}/positions` | 直接编辑/同步持仓快照（方式B） |
| `GET` | `/api/live-portfolios/{id}/positions` | 持仓历史快照列表 |
| `GET` | `/api/live-portfolios/{id}/positions/latest` | 最新持仓快照 |

#### 信号与净值

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/live-portfolios/{id}/signals` | 系统生成的建议历史 |
| `GET` | `/api/live-portfolios/{id}/signals/latest` | 最新一天的建议 |
| `GET` | `/api/live-portfolios/{id}/nav-daily` | 实盘净值序列（画净值曲线） |

### 12.5 前端页面设计

#### 实盘跟踪列表页 (`/live-trading`)

```
┌──────────────────────────────────────────────────────────────┐
│ 实盘跟踪                                        [创建实盘组合] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 多因子V1-稳健版      🟢运行中     创建于 2025-02-10  │    │
│  │ 总资产: ¥1,052,300   今日: +0.32%  累计: +5.23%     │    │
│  │ 持仓: 5只    上次录入: 2025-02-14                    │    │
│  │ ⚠️ 今日尚未录入操作                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 多因子V2-激进版      ⏸暂停       创建于 2025-01-20  │    │
│  │ 总资产: ¥980,500    今日: --     累计: -1.95%       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### 实盘跟踪详情页 (`/live-trading/[id]`)

```
┌──────────────────────────────────────────────────────────────┐
│ 多因子V1-稳健版  实盘跟踪               [录入今日操作] [停止] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ KPI 概览 ──────────────────────────────────────────────┐ │
│ │ 总资产: ¥1,052,300  现金: ¥520,000  持仓市值: ¥532,300  │ │
│ │ 累计收益: +5.23%   最大回撤: -3.5%  运行天数: 25        │ │
│ │ 上次录入: 2025-02-14  下次建议生成: 今日 18:22           │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ 今日建议（T+1 信号）─────────────────────────────────────┐ │
│ │ 🟢 买入:                                                 │ │
│ │   601318.SH 中国平安  得分:78  建议金额:¥61,384          │ │
│ │ 🔴 卖出:                                                 │ │
│ │   000858.SZ 五粮液    原因:跟踪止损  建议:全部卖出(500股) │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ 净值曲线 ────────────────────┐ ┌─ 当前持仓 ───────────┐ │
│ │ [ECharts: 实盘净值 vs 基准]    │ │ 600519 贵州茅台 100股│ │
│ │                               │ │ 000858 五粮液   500股│ │
│ │                               │ │ ...                  │ │
│ └───────────────────────────────┘ └──────────────────────┘ │
│                                                              │
│ ┌─ 交易记录 ────────────────────────────────────────────────┐ │
│ │ 日期       股票     方向  价格    数量   金额              │ │
│ │ 2025-02-14 600519  买入  1680.50 100   168,050            │ │
│ │ 2025-02-13 000001  卖出  11.20   1000  11,200             │ │
│ │ ...                                                       │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

#### 录入操作弹窗

点击"录入今日操作"后弹出，支持两种录入方式的 Tab 切换：

```
┌──────────────────────────────────────────────┐
│ 录入今日操作                          [关闭]  │
├──────────────────────────────────────────────┤
│ [录入交易]  [同步持仓]                         │
│                                              │
│ ─── 录入交易（Tab 1）───                      │
│                                              │
│ 日期: [2025-02-15]                           │
│ 股票: [600519] 贵州茅台                       │
│ 方向: [买入 ▼]                               │
│ 价格: [1680.50]                              │
│ 数量: [100]                                  │
│ 备注: [按建议买入]                            │
│                                              │
│ [+ 添加更多交易]                              │
│                                              │
│ 已添加:                                      │
│  1. 买入 600519 贵州茅台 100股 @1680.50       │
│  2. 卖出 000001 平安银行 1000股 @11.20        │
│                                              │
│              [取消]  [提交]                    │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ ─── 同步持仓（Tab 2）───                      │
│                                              │
│ 日期: [2025-02-15]                           │
│ 现金余额: [520,000]                          │
│                                              │
│ 持仓列表:                                    │
│  股票      数量     成本价                    │
│  [600519]  [100]   [1680.50]                 │
│  [000858]  [500]   [152.30]                  │
│  [+ 添加股票]                                │
│                                              │
│ ⚠️ 同步持仓会覆盖当日通过交易推导的持仓快照     │
│                                              │
│              [取消]  [确认同步]                │
└──────────────────────────────────────────────┘
```

### 12.6 录入方式设计

提供两种互补的录入方式，适应不同场景：

#### 方式A：录入交易

- **适用场景：** 用户当日有明确的买卖操作
- **流程：** 填写每笔交易的股票、方向、价格、数量 → 系统自动推演持仓变化
- **优点：** 交易记录完整，可追溯每笔操作
- **后端逻辑：**
  1. 保存交易记录到 `strategy_portfolio_trades`（`source=manual_input`）
  2. 读取前一日 `strategy_portfolio_positions_daily` 快照
  3. 按交易记录自动推演当日持仓
  4. 生成当日 `strategy_portfolio_positions_daily`（`source: trade_derived`）

#### 方式B：直接同步持仓

- **适用场景：** 初始化组合、修正偏差、或用户不想逐笔录入
- **流程：** 直接填写当前持有的股票和数量 → 系统直接保存
- **优点：** 操作简单，适合快速同步
- **注意：** 会覆盖当日通过交易推导的持仓快照
- **后端逻辑：**
  1. 直接保存到 `strategy_portfolio_positions_daily`（`source: manual_sync`）
  2. 更新 `strategy_portfolios.current_cash`

#### 两种方式的选择建议

| 场景 | 推荐方式 |
|------|------|
| 首次创建实盘组合 | 方式B（直接同步当前真实持仓） |
| 每日正常操作 | 方式A（录入当天的买卖） |
| 持仓与系统记录有偏差 | 方式B（直接修正） |
| 长时间未录入后恢复 | 方式B（重新同步当前持仓） |

### 12.7 信号推送集成

实盘跟踪产出的信号可与模拟盘共用推送通道（Section 7），推送内容增加"实盘"标记：

```
📊 Freedom Quant 实盘建议 (2025-02-15)
策略: 多因子V1 - 稳健版
市场状态: 震荡
基于您的真实持仓生成

🟢 买入建议 (1只):
  601318.SH 中国平安  得分:78  建议金额:¥61,384

🔴 卖出建议 (1只):
  000858.SZ 五粮液  原因:跟踪止损  建议全部卖出(500股)

📈 实盘净值: 累计+5.23%  今日+0.32%
💰 可用资金: ¥520,000
```

---

## 13. 需求不明确项与默认决策

以下决策已按你确认口径固化，可直接作为开发基线。

| # | 决策项 | 最终约束 |
|---|---|---|
| 1 | 术语统一 | `trade_date`=交易日；`signal_date`=信号日(T)；`signal_trade_date`=信号对应成交日(T+1) |
| 2 | T+1 成交限制 | 信号在 `signal_date` 生成，撮合在 `signal_trade_date` 执行；开盘涨停不可买、开盘跌停不可卖 |
| 3 | 分数范围 | 全部统一 `0-100` |
| 4 | 信号表 | 统一使用 `strategy_signals_daily`；旧 `daily_signal` 不参与新系统 |
| 5 | 版本并发 | 同一 `strategy_version_id` 每种类型最多 1 个活跃组合（`running/paused`）；`stopped` 可新建 |
| 6 | 实盘未录入 | 当日未录入按“无操作”处理；允许次日补录并触发从补录日起的重算 |
| 7 | 手续费 | 统一 `commission_rate=0.0005`（万5），不加印花税/滑点 |
| 8 | 指数口径 | 大盘趋势使用 `000001.SH`（上证指数）；策略业绩对比使用 `000905.SH`（中证500） |
| 9 | 可交易范围 | 沿用当前范围：上证主板/深证主板/科创板/创业板；排除北交所 |
| 10 | 推送与配置 | 推送记录落库并更新发送状态；支持飞书多群推送；新增飞书群配置页 |
| 11 | 页面迁移 | 保留旧页并改名 `Daily Signals(旧)`；新增 `Daily Signals` 页面展示新信号 |
| 12 | 运行方式 | 先手动执行 nightly 脚本，不依赖 scheduler 自动触发 |
| 13 | 状态机表达 | 取消 `lifecycle_status`，改为能力位：`paper_enabled`、`live_tracking_enabled`、`push_enabled` |
| 14 | 组合唯一约束 | 仅对活跃状态（`running/paused`）做唯一；`stopped` 后允许新建同类型组合 |
| 15 | 策略级信号主键 | `strategy_signals_daily.portfolio_id` 不使用 `null`，统一占位值 `__strategy__` |
| 16 | 重算与推送 | `recompute_from_date` 默认只重算不重发；仅 `resend=true` 时重发消息 |
| 17 | 手动补录截止 | 每日 `18:20`（Asia/Shanghai）为当日录入截止；超时标记 `late_input=true` 并走补录重算 |
| 18 | 手续费取整 | 每笔 `fee=round(amount*0.0005, 2)` |
| 19 | 路由收敛 | 过渡期使用 `/daily-signals-v2`，稳定后切换为 `/daily-signals` |
| 20 | 旧页下线策略 | 旧页改为 `/daily-signals-legacy` 并保留 8 周，页面显示 deprecated 与下线日期 |

### 13.1 术语混用审计（已检查当前项目）

当前代码里存在命名混用，需作为开发待办统一：

1. 旧信号链路使用 `trading_date`：`backend/scripts/daily/calculate_signal.py`、`backend/app/api/routes/daily_signals.py`。
2. 回测引擎日志混用 `signal_date/exec_date`：`backend/app/quant/engine.py`。
3. 订单与成交混用 `signal_trade_date/trade_date`：`backend/app/quant/execution.py`。
4. `strategy_signals_daily` 目前仅在索引初始化中出现，未被业务读写：`backend/app/data/mongo_backtest.py`。

**待办（命名统一）：**

1. 新系统所有信号接口/集合字段统一改为 `signal_date`、`signal_trade_date`。
2. 旧系统字段 `trading_date` 保留仅供 `Daily Signals(旧)` 页面使用，不再扩展。
3. 文档/API 入参禁止使用 `exec_date`、`exec_trade_date`，统一映射为 `signal_trade_date`。

### 13.2 策略冻结（Freeze）机制

为保证“回测通过后发布到实盘”的可复现性，新增冻结约束：

1. `strategy_versions` 发布时强制填写 `code_ref`（Git commit hash，不允许 branch 名）。
2. 新增 `engine_version`（如 `quant-engine@1.0.0`）和 `data_schema_version`。
3. 新增 `frozen_at`、`frozen_by` 字段；`frozen=true` 后只允许新建 run，不允许改 `params_snapshot`。
4. 回测/信号任务启动前校验：当前运行代码 commit 必须匹配 `code_ref`，否则任务拒绝执行并记录错误。

---

## 14. 代码架构设计（与当前仓库对齐）

### 14.1 设计原则

1. 复用 `app/quant`，不复制策略逻辑。
2. 新增“单日信号计算 + 组合状态编排”层，不改坏现有回测链路。
3. 数据访问继续放 `backend/app/data/`，业务编排放 `backend/app/services/`，路由放 `backend/app/api/routes/`。
4. 与现有命名风格保持一致：`backtest_*`、`strategy_*`。

### 14.2 建议新增模块

```
backend/app/
  services/
    strategy_signal_service.py          # 单日信号计算入口（复用 quant 因子与规则）
    strategy_portfolio_service.py       # 模拟盘/实盘组合管理、状态流转
    strategy_order_service.py           # 模拟盘 pending/filled 订单结算
    strategy_notification_service.py    # 推送编排与重试
  data/
    mongo_strategy_portfolio.py         # 组合、净值、持仓、交易、订单
    mongo_strategy_signal.py            # strategy_signals_daily 读写
    mongo_strategy_notification.py      # 推送记录
    mongo_strategy_feishu_group.py      # 飞书群配置
    mongo_strategy_job_run.py           # 调度任务运行记录（幂等追踪）
  api/routes/
    strategy_signals.py                 # 新信号接口（替代旧 daily_signals）
    paper_portfolios.py                 # 模拟盘接口
    live_portfolios.py                  # 实盘跟踪接口
    strategy_feishu_groups.py           # 飞书群配置接口
```

### 14.3 复用与解耦边界

1. `app/quant` 继续负责：市场状态、打分、买卖规则、仓位建议。
2. `strategy_signal_service` 负责：单日加载数据、调用 quant 计算、产出标准化信号行。
3. `strategy_order_service` 负责：模拟盘 T+1 撮合与持仓/现金更新。
4. `strategy_portfolio_service` 负责：能力位状态（paper/live/push）、页面聚合视图。

### 14.4 调度脚本建议

```
backend/scripts/daily/
  generate_strategy_signals.py          # 生成 T 日信号（signal_trade_date=T+1）
  settle_strategy_orders.py             # 结算 signal_trade_date=T 的 pending 订单
  refresh_strategy_portfolios.py        # 更新组合净值快照、统计字段
  push_strategy_notifications.py        # 推送并记录结果
```

---

## 15. 数据库结构设计（推荐统一模型）

为降低复杂度，建议用“统一组合模型”覆盖模拟盘与实盘跟踪：`portfolio_type` 区分来源。

### 15.1 `strategy_portfolios`

主表，记录组合元信息。

关键字段：

1. `portfolio_id`（字符串UUID，唯一）
2. `portfolio_type`（`paper` / `live`）
3. `strategy_id`、`strategy_version_id`
4. `status`（`running` / `paused` / `stopped`）
5. `initial_capital`、`current_cash`、`current_nav`
6. `start_date`、`last_signal_date`、`last_settle_date`、`last_input_date`
7. `notification_config`（渠道、目标）
8. `created_at`、`updated_at`

索引建议：

1. unique(`portfolio_id`)
2. index(`portfolio_type`, `status`, `updated_at desc`)
3. index(`strategy_version_id`, `portfolio_type`, `status`)
4. partial unique(`strategy_version_id`, `portfolio_type`) where `status in ["running","paused"]`
说明：同版本每种类型最多一个“活跃组合”，`stopped` 后允许新建

### 15.2 `strategy_signals_daily`

单条标的级信号主表（单行一标的，便于分页、筛选、统计）。

关键字段：

1. `signal_date`（信号日 T）
2. `signal_trade_date`（计划成交日 T+1）
3. `strategy_id`、`strategy_version_id`
4. `portfolio_id`（不可为空；策略级信号统一为 `__strategy__`）
5. `portfolio_type`（`paper` / `live` / `strategy`）
6. `ts_code`、`signal`（BUY/SELL/HOLD/BUY_ROTATE/SELL_ROTATE）
7. `score`、`raw_score`、`rank`
8. `target_weight`、`target_amount`
9. `reason_codes`、`market_regime`
10. `generated_at`

索引建议：

1. unique(`signal_date`, `strategy_version_id`, `portfolio_id`, `ts_code`)
2. index(`signal_date desc`, `portfolio_type`, `signal`)
3. index(`portfolio_id`, `signal_date desc`, `score desc`)

### 15.3 `strategy_portfolio_orders`

仅模拟盘使用，承载 T 日生成、T+1 结算的订单。

关键字段：

1. `order_uid`（唯一）
2. `portfolio_id`、`strategy_version_id`
3. `signal_date`、`signal_trade_date`
4. `ts_code`、`side`、`signal_type`
5. `target_weight`、`target_amount`
6. `status`（`pending` / `filled` / `cancelled` / `rejected`）
7. `fill_price`、`fill_qty`、`fill_amount`
8. `can_trade_reason`

索引建议：

1. unique(`order_uid`)
2. index(`portfolio_id`, `signal_trade_date`, `status`)
3. index(`signal_date`, `strategy_version_id`)

### 15.4 `strategy_portfolio_positions_daily`

组合每日持仓快照（paper/live 通用）。

关键字段：

1. `portfolio_id`、`trade_date`、`ts_code`
2. `shares`、`cost_price`、`market_price`、`market_value`
3. `weight`、`pnl`、`return_pct`
4. `source`（`trade_derived` / `manual_sync` / `simulated_fill`）

索引建议：

1. unique(`portfolio_id`, `trade_date`, `ts_code`)
2. index(`portfolio_id`, `trade_date desc`)

### 15.5 `strategy_portfolio_nav_daily`

组合每日净值序列。

关键字段：

1. `portfolio_id`、`trade_date`
2. `nav`、`cash`、`position_value`
3. `daily_return`、`cum_return`、`drawdown`
4. `benchmark_nav`、`benchmark_return`（默认 `000905.SH`）

索引建议：

1. unique(`portfolio_id`, `trade_date`)
2. index(`portfolio_id`, `trade_date desc`)

### 15.6 `strategy_portfolio_trades`

成交明细。paper 来自撮合，live 来自用户录入。

关键字段：

1. `trade_uid`（唯一）
2. `portfolio_id`、`trade_date`、`ts_code`
3. `side`、`price`、`qty`、`amount`
4. `fee`（万5，`round(amount*0.0005, 2)`） 、`slippage_cost`（默认0） 、`realized_pnl`
5. `source`（`simulated` / `manual_input`）

索引建议：

1. unique(`trade_uid`)
2. index(`portfolio_id`, `trade_date desc`)
3. index(`portfolio_id`, `ts_code`, `trade_date desc`)

### 15.7 `strategy_notifications`

推送审计表。

关键字段：

1. `notify_uid`（去重键）
2. `signal_date`、`strategy_version_id`、`portfolio_id`
3. `channel`、`target`
4. `status`（`success` / `failed` / `skipped`）
5. `retry_count`、`error_message`
6. `created_at`、`sent_at`

索引建议：

1. unique(`notify_uid`)
2. index(`signal_date desc`, `status`)

### 15.8 `strategy_job_runs`

调度任务运行日志（排障与幂等判断）。

关键字段：

1. `job_name`、`run_date`
2. `status`、`started_at`、`ended_at`
3. `stats`（写入数、跳过数、失败数）
4. `error_message`

索引建议：

1. unique(`job_name`, `run_date`)
2. index(`run_date desc`, `job_name`)

### 15.9 `strategy_feishu_groups`

飞书群机器人配置表（支持多群推送）。

关键字段：

1. `group_id`（唯一）
2. `group_name`
3. `webhook_url`（加密存储）
4. `secret`（可选，加密存储）
5. `enabled`
6. `created_at`、`updated_at`

索引建议：

1. unique(`group_id`)
2. index(`enabled`, `updated_at desc`)

### 15.10 `strategy_versions` 扩展字段（能力位）

用于表达策略版本是否开启模拟盘、实盘跟踪、推送，不再使用单字段 `lifecycle_status`。

关键字段：

1. `paper_enabled`（bool）
2. `live_tracking_enabled`（bool）
3. `push_enabled`（bool）
4. `paper_portfolio_id`、`live_portfolio_id`（可选）
5. `frozen`、`frozen_at`、`frozen_by`
6. `code_ref`、`engine_version`、`data_schema_version`

---

## 16. 运行与数据流（可直接开发）

### 16.1 日终任务顺序（当前手动执行）

以交易日 `T` 为例，建议拆成两段：

1. EOD(T)：
2. `pull_daily_history.py` / `sync_stk_factor_pro.py` / `sync_zhishu_data.py` 完成 `T` 日数据落库。
3. `generate_strategy_signals.py`：生成 `signal_date=T`、`signal_trade_date=T+1` 的信号。
4. `push_strategy_notifications.py`：发送 `signal_date=T` 信号摘要。
5. EOD(T+1)：
6. `settle_strategy_orders.py`：结算 `signal_trade_date=T+1` 的 pending 订单（用 `T+1` 开盘价）。
7. `refresh_strategy_portfolios.py`：更新 `T+1` 日净值与持仓快照。

### 16.2 幂等规则

1. 所有写入用 upsert。
2. 订单结算以 `order_uid` 和 `status=pending` 为唯一处理入口。
3. 推送以 `notify_uid` 去重，发送后更新 `status=success`。
4. 任务级去重以 `strategy_job_runs(job_name, run_date)` 控制。
5. 重算任务默认 `resend=false`（只更新数据不重发消息）；仅显式 `resend=true` 时重发。

### 16.3 数据就绪门禁

在生成信号前检查：

1. `trade_calendar`：`T` 为开市日。
2. `raw/daily`、`raw/daily_basic`、`features/indicators`：`T` 数据存在且覆盖率达阈值。
3. `shenwan_daily`、`market_index_dailybasic`：`T` 数据存在。

不满足则任务标记 `degraded` 并跳过信号产出，避免脏信号。

### 16.4 手动执行命令（当前默认）

```bash
# 1) 日线/因子/指数数据先同步
bash backend/scripts/daily/daily.sh --start-date 20260206 --end-date 20260206

# 2) 生成信号（signal_date=T, signal_trade_date=T+1）
python backend/scripts/daily/generate_strategy_signals.py --signal-date 20260206

# 3) 到下一交易日再结算上一信号日的 pending 订单
python backend/scripts/daily/settle_strategy_orders.py --trade-date 20260207

# 4) 更新组合快照与净值（T+1）
python backend/scripts/daily/refresh_strategy_portfolios.py --trade-date 20260207

# 5) 推送并落库发送状态
python backend/scripts/daily/push_strategy_notifications.py --signal-date 20260206

# 6) 补录后重算（默认不重发消息）
python backend/scripts/daily/generate_strategy_signals.py --recompute-from-date 20260205

# 7) 如需重发消息，显式开启
python backend/scripts/daily/push_strategy_notifications.py --signal-date 20260206 --resend
```

---

## 17. API 设计补充（与现有路由兼容）

### 17.1 新接口建议

1. `GET /api/strategy-signals`：按 `signal_date`、`strategy_version_id`、`portfolio_id`、`signal` 分页查询。
2. `GET /api/strategy-signals/latest`：返回最新交易日的聚合信号。
3. `POST /api/paper-portfolios`、`GET /api/paper-portfolios/*`、`POST /api/paper-portfolios/{id}/enable-push`、`POST /api/paper-portfolios/{id}/disable-push`。
4. `POST /api/live-portfolios`、`GET /api/live-portfolios/*`。
5. `GET/POST/PUT /api/strategy-feishu-groups*`：飞书群配置 CRUD。

### 17.2 兼容策略

1. 过渡期新页面路由使用 `/daily-signals-v2`，仅使用 `GET /api/strategy-signals*`。
2. 旧页面改名 `Daily Signals(旧)`，路由迁移为 `/daily-signals-legacy`，保留 8 周。
3. 稳定后把新页面主路由收敛到 `/daily-signals`，旧路由跳转到新页。
4. 旧页面顶部显示 deprecated 提示与明确下线日期。

---

## 18. 开发落地建议（交付给 AI 开发的边界）

### 18.1 第一阶段（P0，可在当前代码基线快速落地）

1. 实现 `strategy_signal_service.py`，复用 `app/quant` 单日计算。
2. 落地 `strategy_signals_daily` + `strategy_job_runs`。
3. 实现 `generate_strategy_signals.py`（先做策略级信号，不含组合），并支持手动脚本触发。
4. 新增 `Daily Signals` 页面（先 `/daily-signals-v2`，稳定后切到 `/daily-signals`），旧页改名 `Daily Signals(旧)` 并迁移到 `/daily-signals-legacy`。

### 18.2 第二阶段（P1）

1. 落地统一 `strategy_portfolios` 与 `paper` 链路。
2. 实现 `strategy_portfolio_orders` 两阶段撮合。
3. 增加模拟盘列表/详情页面。
4. 增加策略冻结校验（`code_ref` + `engine_version`）。

### 18.3 第三阶段（P1/P2）

1. 实盘录入（交易录入 + 持仓同步）。
2. 实盘信号生成（基于真实持仓）。
3. 飞书多群推送与通知审计。

### 18.4 验收标准（最低）

1. 同一 `signal_date` 重跑任务，数据库无重复脏数据。
2. 同一策略版本，回测单日信号与 `StrategySignalService` 输出一致。
3. 模拟盘订单能在 `signal_trade_date` 正确结算，不提前成交。
4. 页面可按 `signal_date` 查询 BUY/SELL，并可追溯到 `strategy_version_id + params_snapshot`。

---

## 19. 开发前检查清单（执行门禁）

本清单用于开发前评审、联调前自测、上线前准入。  
建议在 PR 模板中逐项打勾，未通过项不得进入上线阶段。

### 19.1 接口契约清单（必须）

1. 统一术语：接口仅使用 `signal_date`、`signal_trade_date`，不新增 `trading_date/exec_date`。
2. `GET /api/strategy-signals` 支持分页参数：`page`、`page_size`、`sort`，并返回 `total`。
3. `GET /api/strategy-signals` 支持过滤参数：`signal_date`、`strategy_version_id`、`portfolio_id`、`signal`。
4. `GET /api/strategies/{id}/versions` 返回能力位：`paper_enabled`、`live_tracking_enabled`、`push_enabled`。
5. 推送能力接口统一命名：`enable-push/disable-push`，不再使用 `promote/demote`。
6. 错误码统一：参数错误 `400`，鉴权失败 `401/403`，不存在 `404`，冲突 `409`，服务异常 `500`。
7. 所有新接口都接入现有鉴权依赖（与其他 `/api/*` 一致）。

### 19.2 数据库与索引清单（必须）

1. `strategy_signals_daily` 建立唯一索引：`(signal_date, strategy_version_id, portfolio_id, ts_code)`。
2. `strategy_portfolios` 建立唯一索引：`portfolio_id`；并建立 partial unique：`(strategy_version_id, portfolio_type)` where `status in [running, paused]`。
3. `strategy_portfolio_orders` 建立唯一索引：`order_uid`；结算查询索引：`(portfolio_id, signal_trade_date, status)`。
4. `strategy_notifications` 建立唯一索引：`notify_uid`。
5. `strategy_job_runs` 建立唯一索引：`(job_name, run_date)`。
6. 索引创建脚本支持幂等（重复执行不报错）。
7. `strategy_signals_daily.portfolio_id` 策略级信号统一写 `__strategy__`，不得写 `null`。

### 19.3 幂等与重跑清单（必须）

1. 信号生成使用 upsert，重跑同一天不重复插入。
2. 订单结算只处理 `status=pending`，并在同事务内落成交结果与状态变更。
3. 推送任务以 `notify_uid` 去重，成功后写 `status=success`，失败写 `status=failed` + `error_message`。
4. 任务运行日志落 `strategy_job_runs`，每次执行必须有开始/结束状态。
5. 支持“补录后重算”：提供 `recompute_from_date` 参数，从指定日期重建信号与组合快照。
6. 重算默认不重发消息（`resend=false`），仅显式 `resend=true` 时重发。

### 19.4 回滚与故障处理清单（必须）

1. 新页面上线前保留 `Daily Signals(旧)`，避免切换中断。
2. 新脚本失败不影响基础行情同步脚本，失败任务可单独重跑。
3. 推送失败不回滚信号数据，只回滚推送状态并允许重发。
4. 所有关键写入前记录 `run_id/job_id`，便于按批次回滚排查。
5. 提供最小回滚策略：关闭新菜单入口 + 停止新脚本执行 + 保留数据库数据只读。
6. 旧页保留 8 周并展示 deprecated + 下线日期，确保可观测迁移窗口。

### 19.5 性能与数据质量清单（建议）

1. `strategy_signals_daily` 单日写入耗时与行数统计入 `strategy_job_runs.stats`。
2. 大查询接口默认分页，禁止无上限全量返回。
3. 信号生成前做数据覆盖率检查，不足阈值时标记 `degraded`。
4. 关键页面首屏接口（signals latest / portfolio overview）需有索引命中。
5. 对 `fee=round(amount*0.0005, 2)` 做一致性校验，误差阈值在 0.01 元内。

### 19.6 发布前演练清单（必须）

1. 演练日 `T`：执行 `daily.sh` -> `generate_strategy_signals.py` -> `push_strategy_notifications.py`。
2. 演练日 `T+1`：执行 `settle_strategy_orders.py` -> `refresh_strategy_portfolios.py`。
3. 验证同一命令重复执行两次，结果无重复、无脏状态。
4. 验证旧页与新页并行可用，互不影响。
5. 验证飞书多群推送：至少 2 个群配置，1 成功 + 1 失败场景均有审计记录。
