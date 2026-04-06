# 板块排名功能需求文档

## 1. 背景与目标

### 1.1 数据源

本功能使用 Tushare 的申万行业日线行情接口：

| API | 接口名 | 功能描述 | 权限要求 |
|-----|--------|----------|----------|
| 申万行业日线行情 | `sw_daily` | 获取申万行业指数的日线行情数据 | 5000积分 |

**接口文档**: https://tushare.pro/document/2?doc_id=327

### 1.2 接口说明

#### 输入参数
| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| ts_code | str | N | 行业代码 |
| trade_date | str | N | 交易日期（YYYYMMDD）|
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

#### 输出参数
| 名称 | 类型 | 说明 |
|------|------|------|
| ts_code | str | 指数代码（如 801010.SI）|
| trade_date | str | 交易日期 |
| name | str | 指数名称（如 农林牧渔）|
| open | float | 开盘点位 |
| low | float | 最低点位 |
| high | float | 最高点位 |
| close | float | 收盘点位 |
| change | float | 涨跌点位 |
| pct_change | float | 涨跌幅（%）|
| vol | float | 成交量（万股）|
| amount | float | 成交额（万元）|
| pe | float | 市盈率 |
| pb | float | 市净率 |
| float_mv | float | 流通市值（万元）|
| total_mv | float | 总市值（万元）|

### 1.3 重要说明：数据特殊性

**该接口返回的数据包含多种类型的指数**：

1. **标准行业指数**（有对应 level）：
   - 一级行业：801010.SI（农林牧渔）、801030.SI（基础化工）等，共31个
   - 二级行业：801016.SI（动物保健II）、801033.SI（化学纤维）等，共134个
   - 三级行业：850111.SI（种子）、850113.SI（粮油种植）等，共346个

2. **特殊综合指数**（无 level，不在 shenwan_industry 表中）：
   - 801001.SI：申万50
   - 801002.SI：申万中小
   - 801003.SI：申万Ａ指
   - 801005.SI：申万创业
   - 其他特殊指数...

### 1.4 业务目标

- 每日拉取申万行业日线行情数据
- 计算各板块的涨跌幅排名
- 支持按一级、二级、三级行业分别查看排名
- 计算 5 日平均排名，识别持续强势/弱势板块
- 前端展示板块排名，辅助投资决策

---

## 2. 数据库设计

### 2.1 是否复用 shenwan_industry 表？

**结论：复用 shenwan_industry 表**

**分析**：
1. `sw_daily` 接口返回的 `ts_code` 格式（如 `801010.SI`）与 `shenwan_industry` 表的 `index_code` 字段格式一致
2. `shenwan_daily` 可以通过 `ts_code` 引用 `shenwan_industry.index_code` 获取 `level` 信息
3. 日线行情数据单独存储在 `shenwan_daily` 表中，职责清晰

**特殊综合指数处理**：
- `sw_daily` 返回的特殊综合指数（申万50、申万中小、申万A指、申万创业等）在 `shenwan_industry` 中不存在
- 这些指数在 `shenwan_daily` 中正常存储，但 `level` 字段为 `null`
- **不参与排名计算**（排名只针对有 `level` 的标准行业指数）

**表关系**：
```
shenwan_industry (已有)              shenwan_daily (新建)
+-------------------+               +-------------------+
| index_code (PK)   | <------------ | ts_code (FK)      |
| industry_name     |               | trade_date        |
| level (1/2/3)     |               | name              |
| ...               |               | pct_change        |
+-------------------+               | level             |
                                    | rank              |
                                    | rank_total        |
                                    | ...               |
                                    +-------------------+
```

### 2.2 新建集合 1: shenwan_daily（申万指数日行情）

**用途**：存储每日的行情数据及排名。

#### 文档结构
```javascript
{
  // === 主键 ===
  "ts_code": "801010.SI",             // 指数代码（引用 shenwan_industry.index_code）
  "trade_date": "20260202",           // 交易日期（YYYYMMDD）
  
  // === 行情数据 ===
  "name": "农林牧渔",                  // 指数名称（冗余存储便于查询）
  "open": 2986.75,                    // 开盘点位
  "high": 3000.50,                    // 最高点位
  "low": 2940.20,                     // 最低点位
  "close": 2946.60,                   // 收盘点位
  "change": -40.15,                   // 涨跌点位
  "pct_change": -1.34,                // 涨跌幅（%）
  "vol": 83532.00,                    // 成交量（万股）
  "amount": 1234567.00,               // 成交额（万元）
  "pe": 28.32,                        // 市盈率
  "pb": 2.66,                         // 市净率
  "float_mv": 12345678.00,            // 流通市值（万元）
  "total_mv": 23456789.00,            // 总市值（万元）
  
  // === 层级信息（从 shenwan_industry 关联获取，冗余存储便于筛选）===
  "level": 1,                         // 行业层级（1/2/3），综合指数为 null
  
  // === 排名信息（计算后写入，仅 level 不为 null 时有效）===
  "rank": 5,                          // 同层级涨幅排名（涨幅最高为 1）
  "rank_total": 31,                   // 同层级总数
  
  // === 元数据 ===
  "created_at": ISODate("2026-02-02T08:00:00Z"),
  "updated_at": ISODate("2026-02-02T08:00:00Z")
}
```

#### 索引设计
```javascript
// 唯一索引：指数代码 + 交易日期
db.shenwan_daily.createIndex(
  { "ts_code": 1, "trade_date": 1 }, 
  { unique: true, name: "idx_ts_code_trade_date" }
)

// 查询索引：交易日期 + 层级（用于排名查询）
db.shenwan_daily.createIndex(
  { "trade_date": 1, "level": 1 },
  { name: "idx_trade_date_level" }
)

// 查询索引：交易日期 + 涨跌幅（用于排序）
db.shenwan_daily.createIndex(
  { "trade_date": 1, "pct_change": -1 },
  { name: "idx_trade_date_pct_change" }
)

// 查询索引：层级 + 交易日期 + 排名
db.shenwan_daily.createIndex(
  { "level": 1, "trade_date": -1, "rank": 1 },
  { name: "idx_level_trade_date_rank" }
)
```

#### 数据示例
```javascript
// 标准行业指数（有 level，参与排名）
{
  "ts_code": "801010.SI",
  "trade_date": "20260202",
  "name": "农林牧渔",
  "open": 2986.75,
  "close": 2946.60,
  "pct_change": -1.34,
  "level": 1,                         // 一级行业
  "rank": 28,                         // 一级行业中排第 28 名
  "rank_total": 31                    // 共 31 个一级行业
}

// 综合指数（无 level，不参与排名）
{
  "ts_code": "801001.SI",
  "trade_date": "20260202",
  "name": "申万50",
  "open": 2972.86,
  "close": 2946.53,
  "pct_change": -0.88,
  "level": null,                      // 综合指数，无层级
  "rank": null,                       // 不参与排名
  "rank_total": null
}
```

### 2.3 5日平均排名（动态计算，无需单独集合）

**设计决策**：不单独创建 `shenwan_rank_avg` 集合，直接从 `shenwan_daily` 动态查询计算。

**理由**：
1. **数据量小**：申万行业约 500 个，5天数据最多 2500 条记录，聚合计算开销极低
2. **查询简单**：MongoDB 聚合管道可高效完成分组计算
3. **减少维护**：少一张表、少一个脚本、避免数据冗余和不一致

**查询示例**（MongoDB 聚合管道）：
```javascript
// 获取指定层级的 5 日平均排名
db.shenwan_daily.aggregate([
  // 1. 筛选最近5个交易日、指定层级
  { $match: { 
      trade_date: { $in: ["20260202", "20260201", "20260131", "20260130", "20260129"] },
      level: 1 
  }},
  // 2. 按 ts_code 分组，计算平均排名
  { $group: {
      _id: "$ts_code",
      name: { $first: "$name" },
      level: { $first: "$level" },
      rank_avg: { $avg: "$rank" },
      pct_sum: { $sum: "$pct_change" },
      ranks: { $push: { date: "$trade_date", rank: "$rank", pct: "$pct_change" } }
  }},
  // 3. 按平均排名排序
  { $sort: { rank_avg: 1 } },
  // 4. 取前10名（持续强势）或后10名（持续弱势）
  { $limit: 10 }
])
```

---

## 3. 后端脚本开发

### 3.1 脚本 1: sync_shenwan_daily.py

**位置**: `backend/scripts/daily/sync_shenwan_daily.py`

**功能**: 从 TuShare sw_daily 接口获取指定日期的申万行业日行情数据，关联 shenwan_industry 获取层级信息，计算排名后存入数据库。

#### 命令行参数
```bash
# 获取指定日期数据
python backend/scripts/daily/sync_shenwan_daily.py --trade-date 20260202

# 获取最近 N 天数据
python backend/scripts/daily/sync_shenwan_daily.py --last-days 5

# 获取日期范围数据
python backend/scripts/daily/sync_shenwan_daily.py --start-date 20260101 --end-date 20260131
```

#### 处理流程
```python
def sync_daily(trade_date: str):
    """同步指定日期的申万行业日行情数据"""
    
    # 1. 调用 TuShare API 获取数据
    pro = ts.pro_api(token)
    df = pro.sw_daily(trade_date=trade_date)
    
    # 2. 数据预处理
    #    - 处理空值
    #    - 确保字段类型正确
    
    # 3. 关联层级信息（复用 shenwan_industry 表）
    #    - 查询 shenwan_industry 表，构建 index_code -> level 映射
    #    - 通过 ts_code 关联获取 level
    #    - 无法关联的（综合指数）level 设为 null
    
    # 4. 计算排名（仅对有 level 的行业指数）
    #    - 按 level 分组
    #    - 在每个 level 内按 pct_change 降序排名
    #    - 写入 rank 和 rank_total 字段
    
    # 5. 写入 shenwan_daily 表
    #    - 使用 upsert 避免重复
    
    # 6. 返回处理结果统计
```

#### 排名计算逻辑
```python
def calculate_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """计算各层级的涨跌幅排名"""
    
    # 初始化排名字段
    df['rank'] = None
    df['rank_total'] = None
    
    # 按 level 分组计算排名（跳过 level 为 null 的综合指数）
    for level in [1, 2, 3]:
        mask = df['level'] == level
        level_df = df[mask].copy()
        
        if level_df.empty:
            continue
        
        # 按涨跌幅降序排名（涨幅最高排名为1）
        level_df['rank'] = level_df['pct_change'].rank(
            ascending=False, 
            method='min'
        ).astype(int)
        level_df['rank_total'] = len(level_df)
        
        df.loc[mask, 'rank'] = level_df['rank']
        df.loc[mask, 'rank_total'] = level_df['rank_total']
    
    return df
```

### 3.2 TuShare Client 扩展

**位置**: `backend/app/data/tushare_client.py`

新增函数：
```python
def fetch_shenwan_daily(trade_date: str) -> pd.DataFrame:
    """获取申万行业日线行情数据"""
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.sw_daily(trade_date=trade_date)
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None:
        return pd.DataFrame()
    return df
```

---

## 4. 后端 API 开发

### 4.1 新增路由文件

**位置**: `backend/app/api/routes/sector_ranking.py`

### 4.2 API 端点设计

#### 4.2.1 获取可用交易日期列表
```
GET /api/sector-ranking/dates
```

**响应示例**:
```json
{
  "items": ["20260202", "20260201", "20260131", "20260130", "20260129"],
  "total": 5
}
```

#### 4.2.2 获取指定日期的板块排名
```
GET /api/sector-ranking/daily
```

**查询参数**:
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| trade_date | str | N | 最新日期 | 交易日期（YYYYMMDD）|
| level | int | N | 1 | 行业层级（1/2/3）|
| top_n | int | N | 5 | 获取涨幅前 N 名 |
| bottom_n | int | N | 5 | 获取跌幅前 N 名 |

**响应示例**:
```json
{
  "trade_date": "20260202",
  "level": 1,
  "total": 31,
  "top": [
    {
      "ts_code": "801080.SI",
      "name": "电子",
      "pct_change": 3.45,
      "rank": 1,
      "close": 5678.90,
      "vol": 123456.00,
      "amount": 7890123.00
    }
  ],
  "bottom": [
    {
      "ts_code": "801010.SI",
      "name": "农林牧渔",
      "pct_change": -2.34,
      "rank": 31,
      "close": 2946.60,
      "vol": 83532.00,
      "amount": 1234567.00
    }
  ]
}
```

#### 4.2.3 获取过去 N 天的板块排名
```
GET /api/sector-ranking/history
```

**查询参数**:
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| days | int | N | 5 | 获取最近 N 天 |
| level | int | N | 1 | 行业层级（1/2/3）|
| top_n | int | N | 5 | 每天获取涨幅前 N 名 |
| bottom_n | int | N | 5 | 每天获取跌幅前 N 名 |

**响应示例**:
```json
{
  "level": 1,
  "days": 5,
  "data": [
    {
      "trade_date": "20260202",
      "top": [...],
      "bottom": [...]
    },
    {
      "trade_date": "20260201",
      "top": [...],
      "bottom": [...]
    }
  ]
}
```

#### 4.2.4 获取 5 日平均排名
```
GET /api/sector-ranking/avg
```

**说明**：从 `shenwan_daily` 动态聚合计算，无需单独存储。

**查询参数**:
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| calc_date | str | N | 最新日期 | 计算基准日期（YYYYMMDD）|
| level | int | N | 1 | 行业层级（1/2/3）|
| top_n | int | N | 10 | 获取平均排名最小的 N 个（持续强势）|
| bottom_n | int | N | 10 | 获取平均排名最大的 N 个（持续弱势）|

**响应示例**:
```json
{
  "calc_date": "20260202",
  "level": 1,
  "trade_dates": ["20260202", "20260201", "20260131", "20260130", "20260129"],
  "strongest": [
    {
      "ts_code": "801080.SI",
      "name": "电子",
      "rank_avg": 2.4,
      "rank_day1": 1,
      "rank_day2": 3,
      "rank_day3": 2,
      "rank_day4": 4,
      "rank_day5": 2,
      "pct_sum": 8.56
    }
  ],
  "weakest": [
    {
      "ts_code": "801010.SI",
      "name": "农林牧渔",
      "rank_avg": 28.6,
      "rank_day1": 30,
      "rank_day2": 28,
      "rank_day3": 29,
      "rank_day4": 27,
      "rank_day5": 29,
      "pct_sum": -5.23
    }
  ]
}
```

---

## 5. 前端页面开发

### 5.1 导航菜单更新

**位置**: `frontend/pages/_app.js`

在顶部导航中新增"板块排名"链接：

```jsx
<div className="nav-links">
  <Link href="/" className="nav-link">首页</Link>
  <Link href="/sectors" className="nav-link">板块</Link>
  <Link href="/sector-ranking" className="nav-link">板块排名</Link>  {/* 新增 */}
  <Link href="/daily-signals" className="nav-link">Daily Signals</Link>
  <Link href="/watchlist" className="nav-link">自选</Link>
  <Link href="/users" className="nav-link">用户管理</Link>
</div>
```

### 5.2 板块排名页面

**位置**: `frontend/pages/sector-ranking.js`

#### 页面布局
```
+------------------------------------------------------------------+
| QUANT PLATFORM                                          [退出]    |
+------------------------------------------------------------------+
|                                                                   |
| 板块排名                                                          |
| 申万行业涨跌幅排名                                                 |
|                                                                   |
+------------------------------------------------------------------+
| 层级选择: [一级行业 ▼]  [二级行业]  [三级行业]                    |
+------------------------------------------------------------------+
|                                                                   |
| 近5日排名                                                         |
| +---------------------------------------------------------------+ |
| |       | 2026-02-02 | 2026-02-01 | 2026-01-31 | 2026-01-30 | ...| |
| +-------+------------+------------+------------+------------+----+ |
| | TOP   |            |            |            |            |    | |
| +-------+------------+------------+------------+------------+----+ |
| | 1     | 电子 +3.45%| 医药 +2.12%| 电子 +1.89%| 汽车 +2.56%| ...| |
| | 2     | 医药 +2.89%| 电子 +1.98%| 汽车 +1.67%| 电子 +2.34%| ...| |
| | 3     | 汽车 +2.34%| 汽车 +1.76%| 医药 +1.45%| 医药 +2.12%| ...| |
| | 4     | ...        | ...        | ...        | ...        | ...| |
| | 5     | ...        | ...        | ...        | ...        | ...| |
| +-------+------------+------------+------------+------------+----+ |
| | BOTTOM|            |            |            |            |    | |
| +-------+------------+------------+------------+------------+----+ |
| | 27    | 农林牧渔   | 钢铁       | 农林牧渔   | 钢铁       | ...| |
| |       | -2.34%     | -1.89%     | -2.12%     | -1.67%     | ...| |
| | ...   | ...        | ...        | ...        | ...        | ...| |
| | 31    | 钢铁 -3.12%| 农林牧渔   | 钢铁       | 农林牧渔   | ...| |
| |       |            | -2.45%     | -2.89%     | -2.34%     | ...| |
| +-------+------------+------------+------------+------------+----+ |
|                                                                   |
+------------------------------------------------------------------+
|                                                                   |
| 5日平均排名                                                       |
| +---------------------------------------------------------------+ |
| | 持续强势板块（平均排名最小）                                    | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
| | 排名  | 板块   | 平均 | D1 | D2 | D3 | D4 | D5 | 5日累计| 操作 | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
| | 1     | 电子   | 2.4  | 1  | 3  | 2  | 4  | 2  | +8.56%| 查看 | |
| | 2     | 医药   | 3.2  | 2  | 1  | 4  | 3  | 6  | +7.23%| 查看 | |
| | ...   | ...    | ...  | ...| ...| ...| ...| ...| ...   | ...  | |
| | 10    | ...    | ...  | ...| ...| ...| ...| ...| ...   | ...  | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
| |                                                                | |
| | 持续弱势板块（平均排名最大）                                    | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
| | 排名  | 板块   | 平均 | D1 | D2 | D3 | D4 | D5 | 5日累计| 操作 | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
| | 1     | 农林牧渔| 28.6| 30 | 28 | 29 | 27 | 29 | -5.23%| 查看 | |
| | 2     | 钢铁   | 27.8 | 31 | 29 | 30 | 28 | 21 | -4.89%| 查看 | |
| | ...   | ...    | ...  | ...| ...| ...| ...| ...| ...   | ...  | |
| | 10    | ...    | ...  | ...| ...| ...| ...| ...| ...   | ...  | |
| +-------+--------+------+----+----+----+----+----+-------+------+ |
+------------------------------------------------------------------+
```

### 5.3 交互设计

#### 层级切换
- 点击"一级行业"、"二级行业"、"三级行业"切换显示
- 一级行业显示 top/bottom 各 5 个
- 二级行业显示 top/bottom 各 10 个
- 三级行业显示 top/bottom 各 10 个

#### 涨跌幅样式
- 涨幅为正：红色（change-up）
- 涨幅为负：绿色（change-down）
- 涨幅为零：灰色（change-flat）

#### 排名颜色
- TOP 区域：背景淡红色
- BOTTOM 区域：背景淡绿色

#### 跳转功能
- 点击板块名称可跳转到板块详情页（/sectors/{index_code}）
- "查看"按钮同样跳转到板块详情页

---

## 6. 调度任务配置

### 6.1 调度接入说明

该能力的日常同步应接入：

- `backend/scripts/daily/daily.sh`
- 或后续统一迁入 Airflow

**注**：5日平均排名无需单独计算任务，API 查询时从 `shenwan_daily` 动态聚合计算。

---

## 7. 开发检查清单

### 阶段 1: 数据层开发

- [x] 新增 `backend/app/data/mongo_shenwan_daily.py`
  - [x] 实现 shenwan_daily 集合的 CRUD 操作
  - [x] 创建必要的索引
  - [x] 实现关联 shenwan_industry 获取 level 的逻辑
  - [x] 实现 5 日平均排名的聚合查询函数

- [x] 扩展 `backend/app/data/tushare_client.py`
  - [x] 新增 `fetch_shenwan_daily(trade_date: str)` 函数

### 阶段 2: 脚本开发

- [x] 新增 `backend/scripts/daily/sync_shenwan_daily.py`
  - [x] 实现数据拉取逻辑
  - [x] 实现通过 ts_code 关联 shenwan_industry.index_code 获取 level
  - [x] 实现排名计算逻辑（仅对有 level 的行业指数）
  - [x] 实现数据写入逻辑
  - [x] 支持命令行参数（--trade-date, --last-days, --start-date, --end-date）

### 阶段 3: API 开发

- [x] 新增 `backend/app/api/routes/sector_ranking.py`
  - [x] 实现 `GET /api/sector-ranking/dates`
  - [x] 实现 `GET /api/sector-ranking/daily`
  - [x] 实现 `GET /api/sector-ranking/history`
  - [x] 实现 `GET /api/sector-ranking/avg`

- [x] 更新 `backend/app/api/routers.py`
  - [x] 注册 sector_ranking 路由

### 阶段 4: 前端开发

- [x] 更新 `frontend/pages/_app.js`
  - [x] 在导航栏新增"板块排名"链接

- [x] 新增 `frontend/pages/sector-ranking.js`
  - [x] 实现层级选择 Tab
  - [x] 实现近 5 日排名表格
  - [x] 实现 5 日平均排名面板（强势/弱势板块）
  - [x] 实现涨跌幅颜色样式
  - [x] 实现跳转到板块详情页功能

- [x] 更新 `frontend/styles/globals.css`
  - [x] 新增板块排名相关样式

### 阶段 5: 调度任务配置

- [ ] 将 `sync_shenwan_daily` 挂入统一脚本链路或 Airflow 编排

### 阶段 6: 测试与验收

- [ ] 手动执行脚本验证数据拉取和计算
- [ ] 验证 API 返回数据正确性
- [ ] 验证前端页面展示效果
- [ ] 验证调度任务执行情况

---

## 8. 注意事项

### 8.1 API 调用限制
- TuShare sw_daily 接口单次最大 4000 行
- 按 trade_date 单日获取可避免超限
- 建议在 API 调用间隔 sleep 0.3 秒

### 8.2 层级关联（复用 shenwan_industry 表）
- sw_daily 返回的 ts_code（如 801010.SI）与 shenwan_industry 的 index_code 格式一致
- 通过 ts_code 关联 shenwan_industry.index_code 获取 level 信息
- 部分指数（申万50、申万中小等）在 shenwan_industry 中不存在，level 设为 null
- 关联失败时不影响数据存储，仅 level 为 null，不参与排名计算

### 8.3 排名计算
- 排名按涨跌幅降序排列，涨幅最高排名为 1
- 同一涨跌幅使用 min 方法排名（相同涨幅取最小排名）
- **只对 level 不为 null 的行业指数计算排名**
- 综合指数（申万50等）不参与排名，rank 字段为 null

### 8.4 5日平均排名
- 无需单独存储，API 查询时从 `shenwan_daily` 动态聚合计算
- 如果某天数据缺失，使用可用天数计算平均值

---

## 9. 相关文档

- [申万行业数据存储需求文档](./shenwan_classify.md)
- [TuShare sw_daily 接口文档](https://tushare.pro/document/2?doc_id=327)
