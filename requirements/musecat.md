# MuseCat 策略独立化改造需求与实施说明

## 1. 目标

在现有策略中心中新增 `MuseCat` 策略，并保证与现有 `Alpha(=multifactor_v1)` 完全独立：

1. 策略代码独立：`multifactor_v1` 与 `musecat_v1` 分别加载不同实现。
2. 参数独立：不同策略键使用不同参数 Schema 和默认值。
3. 回测可复现：每个 `run_id` 绑定 `strategy_version_id + strategy_key + params_snapshot`。
4. 向后兼容：历史 Alpha 策略与回测记录保持可用。

---

## 2. 设计约束（已定）

1. 旧 Alpha 继续使用策略键 `multifactor_v1`，不重命名。
2. 每个 `strategy_id` 强制绑定一个 `strategy_key`，禁止跨版本切换策略代码。
3. 前后端都做参数隔离：
   - 后端是最终校验真相源。
   - 前端根据策略键动态展示参数表单，减少误填。

---

## 3. 数据模型改造

### 3.1 `strategy_definitions`

新增字段：

- `strategy_key: str`（示例：`multifactor_v1` / `musecat_v1`）

新增索引：

- `(strategy_key, status, updated_at)`

### 3.2 `strategy_versions`

新增字段：

- `strategy_key: str`
- `params_schema_version: str`（当前为 `v1`）

新增索引：

- `(strategy_id, strategy_key, created_at)`

### 3.3 `backtest_runs`

新增字段：

- `strategy_key: str`

新增索引：

- `(strategy_key, created_at)`

---

## 4. 后端改造清单

### 4.1 策略注册与实现

- 在 `backend/app/quant/base.py` 新增：`MuseCatV1Strategy`。
- 在 `backend/app/quant/registry.py` 注册：`musecat_v1`。

### 4.2 参数注册与校验中心

新增文件：`backend/app/quant/params_registry.py`

职责：

1. 维护支持的策略键：`multifactor_v1`, `musecat_v1`
2. 为不同策略键提供默认参数模板
3. 做参数白名单校验（禁止跨策略参数混用）
4. 归一化参数数值类型（int/float/bool/list）
5. 统一输出：`(normalized_params, params_schema_version)`

### 4.3 策略服务层

文件：`backend/app/services/strategy_service.py`

改造：

1. `create_strategy` 增加 `strategy_key` 入参，并校验策略键必须已注册。
2. 发布版本时：
   - 从 strategy definition 读取绑定策略键。
   - 校验 `params_snapshot.strategy_key`（若传）必须与 definition 一致。
   - 调用 `validate_and_normalize_params`，保存标准化快照。
   - 写入 `strategy_versions.strategy_key` 和 `params_schema_version`。

### 4.4 回测服务层

文件：`backend/app/services/backtest_service.py`

改造：

1. 创建 run 时校验 definition 与 version 的 `strategy_key` 一致。
2. 将 `strategy_key` 快照写入 `backtest_runs`。

### 4.5 信号服务层

文件：`backend/app/services/strategy_signal_service.py`

改造：

1. 不再只依赖 `params_snapshot.strategy_key`。
2. 优先读取 `strategy_versions.strategy_key` 选择策略实现。
3. 每次计算前先做 `validate_and_normalize_params`，确保版本参数可用且独立。

### 4.6 回测脚本入口

文件：`backend/scripts/backtest/run_backtest.py`

改造：

1. 使用版本绑定的 `strategy_key` 作为策略加载依据。
2. `--strategy-key` 仅用于一致性校验：
   - 传了且与版本不一致 => 直接报错。
3. 运行前统一走参数规范化。

### 4.7 API 变更

文件：`backend/app/api/routes/strategies.py`

改造：

- `POST /api/strategies` 请求体新增必填：`strategy_key`。

---

## 5. 前端改造清单

文件：`frontend/pages/strategies.js`

### 5.1 创建策略

- 新增 `策略键` 下拉（`multifactor_v1` / `musecat_v1`）。
- 提交创建策略时携带 `strategy_key`。

### 5.2 列表展示

- 策略列表新增 `策略键` 列。
- 版本列表新增 `策略键` 列。

### 5.3 版本参数编辑

1. `strategy_key` 在版本表单中只读显示（绑定于策略，不可编辑）。
2. 根据当前策略键动态渲染参数字段：
   - `multifactor_v1`: 显示 `factor_weights.*`
   - `musecat_v1`: 显示 `musecat_factor_weights.*`, `musecat_breakout_bonus`, `musecat_drawdown_penalty`
3. 构造 `params_snapshot` 时按策略键生成，避免发送另一策略的字段。

---

## 6. 一次性迁移脚本

新增文件：`backend/scripts/one_time/backfill_strategy_engine_key.py`

用途：

1. 回填历史 `strategy_definitions.strategy_key`
2. 回填历史 `strategy_versions.strategy_key`
3. 回填 `strategy_versions.params_schema_version`（缺失时为 `v1`）
4. 检测并输出同一 `strategy_id` 下多个 `strategy_key` 的冲突

用法：

```bash
# 预览
python backend/scripts/one_time/backfill_strategy_engine_key.py --dry-run

# 执行
python backend/scripts/one_time/backfill_strategy_engine_key.py
```

---

## 7. 验收标准

1. 能创建 `strategy_key=multifactor_v1` 和 `strategy_key=musecat_v1` 两类策略。
2. 同一策略下发布版本时，参数混用会被后端阻断（HTTP 400）。
3. 新建回测 run 后，`backtest_runs` 含正确 `strategy_key`。
4. `run_backtest.py` 在 CLI 覆盖策略键不一致时失败退出。
5. 前端在 MuseCat 策略下不再展示 Alpha 专属参数输入。
6. 历史 Alpha 版本与回测查询仍可正常使用。

---

## 8. 风险与处理

1. 历史数据缺少 `strategy_key`
   - 用迁移脚本统一回填，默认 `multifactor_v1`。
2. 历史存在混合版本
   - 脚本输出冲突列表，人工拆分策略定义。
3. 前端旧页面缓存
   - 发布后提示用户强刷；API 仍以服务端校验兜底。

---

## 9. 发布建议

1. 先部署后端（含兼容读取与校验）。
2. 执行回填脚本并处理冲突。
3. 再部署前端动态表单。
4. 用 Alpha + MuseCat 各跑一次回测做冒烟验证。
