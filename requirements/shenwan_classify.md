# 申万行业数据存储需求文档

## 1. 背景与目标

### 1.1 数据源
本功能涉及两个 Tushare API：

| API | 接口名 | 功能描述 | 权限要求 |
|-----|--------|----------|----------|
| 行业分类定义 | `index_classify` | 获取申万行业分类的层级结构 | 2000积分 |
| 行业成分构成 | `index_member_all` | 获取股票与行业的对应关系 | 2000积分 |

**数据版本**: 
- 2014版：28个一级分类，104个二级分类，227个三级分类
- 2021版：31个一级分类，134个二级分类，346个三级分类

### 1.2 业务目标
- 存储申万行业分类的层级结构数据（`index_classify`）
- 存储股票与行业的关联关系，支持历史变更追溯（`index_member_all`）
- 支持按行业查询成分股、按股票查询所属行业
- 支持历史版本追溯（2014版 vs 2021版）

---

## 2. API 数据字段说明

### 2.1 API 1: index_classify（行业分类定义）

#### 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| src | str | N | 来源（SW2014/SW2021）|
| level | str | N | 行业等级（L1/L2/L3）|

#### 返回字段
| 字段名 | 类型 | 示例值 | 说明 |
|--------|------|--------|------|
| 行业代码 | str | "110000" / "110100" / "110101" | 层级编码 |
| 指数代码 | str | "801010" / "801016" / "850111" | 申万指数代码 |
| 一级行业 | str | "农林牧渔" | 一级行业名称 |
| 二级行业 | str | "种植业" / null | 二级行业名称（可能为空）|
| 三级行业 | str | "种子" / null | 三级行业名称（可能为空）|
| 指数类别 | str | "一级行业" / "二级行业" / "三级行业" | 层级类型 |
| 是否发布 | int | 1 / 0 | 1=发布，0=不发布 |
| 变动原因 | str | "2021保留" / "2021新增" / "2021改名" | 版本变更说明 |
| 成分股数 | int | 100 | 该行业成分股数量 |

### 2.2 API 2: index_member_all（行业成分构成）

#### 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| l1_code | str | N | 一级行业代码 |
| l2_code | str | N | 二级行业代码 |
| l3_code | str | N | 三级行业代码 |
| ts_code | str | N | 股票代码 |
| is_new | str | N | 是否最新（默认为"Y"）|

#### 返回字段
| 字段名 | 类型 | 示例值 | 说明 |
|--------|------|--------|------|
| l1_code | str | "801050.SI" | 一级行业代码（指数代码）|
| l1_name | str | "有色金属" | 一级行业名称 |
| l2_code | str | "801053.SI" | 二级行业代码（指数代码）|
| l2_name | str | "贵金属" | 二级行业名称 |
| l3_code | str | "850531.SI" | 三级行业代码（指数代码）|
| l3_name | str | "黄金" | 三级行业名称 |
| ts_code | str | "600547.SH" | 成分股票代码 |
| name | str | "山东黄金" | 成分股票名称 |
| in_date | str | "20030826" | 纳入日期（YYYYMMDD）|
| out_date | str | "20220101" / null | 剔除日期（YYYYMMDD，null表示未剔除）|
| is_new | str | "Y" / "N" | 是否最新（Y=当前成分股，N=历史成分股）|

#### 调用方式说明
```python
# 方式1：已知行业，查成分股（按三级行业查）
df = pro.index_member_all(l3_code='850531.SI')

# 方式2：已知股票，查所属行业
df = pro.index_member_all(ts_code='000001.SZ')

# 方式3：获取所有最新成分股（is_new='Y'）
df = pro.index_member_all(is_new='Y')
```

---

## 3. 数据库选型

### 3.1 选型决策
**选择 MongoDB**

**理由**:
1. **与现有架构一致**: 项目已使用 MongoDB 存储业务数据（daily_signal, stock_basic 等）
2. **数据结构灵活**: 行业分类数据为树状层级结构，MongoDB 的文档模型更适合存储
3. **时间序列友好**: 成分股的 in_date/out_date 可以方便地记录历史变更
4. **数据量适中**: 两个版本总共约 500+ 行业，5000+ 股票关联记录

---

## 4. 表结构设计

### 4.1 集合 1: shenwan_industry（行业分类定义）

#### 文档结构
```javascript
{
  // === 核心字段 ===
  "industry_code": "110101",           // 行业代码（唯一标识）
  "index_code": "850111",              // 申万指数代码
  "industry_name": "种子",             // 行业名称（末级名称）
  
  // === 层级结构 ===
  "level": 3,                          // 层级（1/2/3）
  "level_name": "三级行业",             // 层级名称
  
  // === 上级关联（便于快速查询）===
  "parent_code": "110100",             // 父级行业代码（一级、二级为 null）
  "level1_code": "110000",             // 一级行业代码
  "level1_name": "农林牧渔",            // 一级行业名称
  "level2_code": "110100",             // 二级行业代码
  "level2_name": "种植业",              // 二级行业名称
  
  // === 版本信息 ===
  "version": "2021",                   // 版本：2014 或 2021
  "version_note": "2021改名",          // 版本变更说明
  
  // === 状态 ===
  "is_published": true,                // 是否发布
  "constituent_count": 8,              // 成分股数量
  
  // === 元数据 ===
  "created_at": ISODate("2026-02-02T08:00:00Z"),
  "updated_at": ISODate("2026-02-02T08:00:00Z")
}
```

#### 索引设计
```javascript
// 唯一索引：版本 + 行业代码
db.shenwan_industry.createIndex(
  { "version": 1, "industry_code": 1 }, 
  { unique: true, name: "idx_version_industry_code" }
)

// 查询索引：版本 + 层级
db.shenwan_industry.createIndex(
  { "version": 1, "level": 1 },
  { name: "idx_version_level" }
)

// 查询索引：版本 + 一级行业代码
db.shenwan_industry.createIndex(
  { "version": 1, "level1_code": 1 },
  { name: "idx_version_level1" }
)
```

### 4.2 集合 2: shenwan_industry_member（行业成分构成）

#### 文档结构
```javascript
{
  // === 关联标识 ===
  "ts_code": "600547.SH",              // 股票代码
  "name": "山东黄金",                   // 股票名称
  
  // === 行业层级（冗余存储便于查询）===
  "l1_code": "801050.SI",
  "l1_name": "有色金属",
  "l2_code": "801053.SI",
  "l2_name": "贵金属",
  "l3_code": "850531.SI",              // 三级行业代码（关联到 shenwan_industry.index_code）
  "l3_name": "黄金",
  
  // === 时间追踪（核心字段）===
  "in_date": "20030826",               // 纳入日期（YYYYMMDD）
  "out_date": null,                    // 剔除日期（null表示当前仍在该行业）
  "is_new": "Y",                       // 是否最新（Y=是，N=否）
  
  // === 版本控制 ===
  "version": "2021",                   // 版本：2014 或 2021
  
  // === 元数据 ===
  "created_at": ISODate("2026-02-02T08:00:00Z"),
  "updated_at": ISODate("2026-02-02T08:00:00Z")
}
```

#### 索引设计
```javascript
// 唯一索引：股票 + 三级行业 + 纳入日期（同一股票同一行业不同时间可能重复）
db.shenwan_industry_member.createIndex(
  { "ts_code": 1, "l3_code": 1, "in_date": 1 },
  { unique: true, name: "idx_stock_industry_indate" }
)

// 查询索引：三级行业代码 + 是否最新
db.shenwan_industry_member.createIndex(
  { "l3_code": 1, "is_new": 1 },
  { name: "idx_l3code_isnew" }
)

// 查询索引：股票代码 + 是否最新
db.shenwan_industry_member.createIndex(
  { "ts_code": 1, "is_new": 1 },
  { name: "idx_tscode_isnew" }
)

// 查询索引：一级行业代码 + 是否最新
db.shenwan_industry_member.createIndex(
  { "l1_code": 1, "is_new": 1 },
  { name: "idx_l1code_isnew" }
)
```

### 4.3 数据示例

#### shenwan_industry 示例
```javascript
// 三级行业：黄金
{
  "industry_code": "240401",
  "index_code": "850531.SI",           // 与 member.l3_code 关联
  "industry_name": "黄金",
  "level": 3,
  "level_name": "三级行业",
  "parent_code": "240400",
  "level1_code": "240000",
  "level1_name": "有色金属",
  "level2_code": "240400",
  "level2_name": "贵金属",
  "version": "2021",
  "is_published": true,
  "constituent_count": 11
}
```

#### shenwan_industry_member 示例
```javascript
// 山东黄金 - 当前在黄金行业
{
  "ts_code": "600547.SH",
  "name": "山东黄金",
  "l1_code": "801050.SI",
  "l1_name": "有色金属",
  "l2_code": "801053.SI",
  "l2_name": "贵金属",
  "l3_code": "850531.SI",
  "l3_name": "黄金",
  "in_date": "20030826",
  "out_date": null,                     // null 表示当前仍在该行业
  "is_new": "Y",
  "version": "2021"
}

// 假设某股票历史上被调整出黄金行业（示例）
{
  "ts_code": "600XXX.SH",
  "name": "某黄金股",
  "l1_code": "801050.SI",
  "l1_name": "有色金属",
  "l2_code": "801053.SI",
  "l2_name": "贵金属",
  "l3_code": "850531.SI",
  "l3_name": "黄金",
  "in_date": "20100101",
  "out_date": "20220101",               // 2022年被剔除
  "is_new": "N",                        // 不是最新
  "version": "2021"
}
```

---

## 5. 关联设计

### 5.1 两个集合的关系
- **`shenwan_industry`**: 存储行业的定义信息（有哪些行业）
- **`shenwan_industry_member`**: 存储股票与行业的关联（哪些股票属于该行业，何时纳入/剔除）

### 5.2 关联字段
```
shenwan_industry.index_code  <--->  shenwan_industry_member.l3_code
（行业指数代码）                  （三级行业代码）
```

### 5.3 与 stock_basic 的关联
**推荐不在 stock_basic 中冗余存储行业代码**，原因：
1. 股票可能在历史上更换过行业（in_date/out_date 记录）
2. 股票可能同时属于多个版本的行业（2014版 vs 2021版）

**查询时通过 member 集合关联**:
```javascript
// 获取某股票的当前行业（通过 member 表）
db.shenwan_industry_member.findOne({ ts_code: "600547.SH", is_new: "Y" })

// 然后获取行业详情
db.shenwan_industry.findOne({ index_code: "850531.SI" })
```

---

## 6. 页面设计

### 6.1 导航设计

#### Tab 结构
在现有顶部导航中新增"板块"Tab，与"股票列表"并列：

```
[Freedom]  [股票列表]  [板块]  [每日信号]  [自选组]  [退出]
```

#### 路由设计
| 页面 | 路由 | 说明 |
|------|------|------|
| 板块首页 | `/sectors` | 展示一级行业列表 |
| 行业详情 | `/sectors/{index_code}` | 展示行业详情及成分股 |

### 6.2 板块首页（/sectors）

#### 页面布局
```
+----------------------------------------------------------+
| 板块                                    [刷新数据]        |
+----------------------------------------------------------+
| 版本选择: [2021版 ▼]  [2014版 ▼]                         |
+----------------------------------------------------------+
| 一级行业列表                                              |
| +--------+--------+--------+--------+--------+--------+  |
| | 农林牧渔| 基础化工|  钢铁  |有色金属|  电子  |  汽车  |  |
| | 801010 | 801030 | 801040 | 801050 | 801080 | 801880 |  |
| | 100只  | 311只  |  43只  | 125只  | 284只  | 221只  |  |
| +--------+--------+--------+--------+--------+--------+  |
| | ...更多一级行业卡片                                     |
| +--------+--------+--------+--------+--------+--------+  |
+----------------------------------------------------------+
```

#### 一级行业卡片元素
- **行业名称**（如：农林牧渔）
- **指数代码**（如：801010）
- **成分股数量**（如：100只）
- **点击进入详情页**

### 6.3 行业详情页（/sectors/{index_code}）

#### 页面布局
```
+----------------------------------------------------------+
| 有色金属 > 贵金属 > 黄金                    [返回板块列表] |
| 指数代码: 850531.SI         成分股: 11只   版本: 2021版   |
+----------------------------------------------------------+
|                                                          |
| [行业走势图表区]（可选，预留位置）                        |
|                                                          |
+----------------------------------------------------------+
| 成分股列表                                    [导出CSV]  |
| +--------+--------+--------+--------+--------+           |
| | 股票代码| 股票名称| 纳入日期| 剔除日期|  状态   |           |
| +--------+--------+--------+--------+--------+           |
| |600547.SH| 山东黄金|2003-08-26|   -    |  在岗   |           |
| |600988.SH| 赤峰黄金|2004-04-14|   -    |  在岗   |           |
| | ...更多成分股                                          |
| +--------+--------+--------+--------+--------+           |
+----------------------------------------------------------+
```

#### 功能说明

**面包屑导航**
- 展示完整层级：一级 > 二级 > 三级
- 点击上级可跳转到对应层级详情

**成分股列表字段**
| 字段 | 说明 |
|------|------|
| 股票代码 | ts_code，可点击跳转股票详情页 |
| 股票名称 | name |
| 纳入日期 | in_date（YYYY-MM-DD）|
| 剔除日期 | out_date（YYYY-MM-DD，在岗显示"-"）|
| 状态 | "在岗"（is_new=Y）/ "已剔除"（is_new=N）|

**筛选功能**
- 默认只展示 is_new='Y'（在岗）的成分股
- 可勾选"显示历史成分股"查看已剔除的股票

### 6.4 关联跳转

#### 从板块页跳转到股票详情
- 点击成分股列表中的股票代码
- 跳转至 `/stocks/{ts_code}`
- returnUrl 携带当前板块页 URL，便于返回

#### 从股票详情查看所属板块
- 在股票详情页（/stocks/{ts_code}）新增"所属板块"卡片
- 展示该股票当前所属的一级/二级/三级行业
- 点击行业名称可跳转至对应板块详情页

### 6.5 权限控制
- 板块页面需要登录访问（与现有页面一致）
- 无需额外权限（所有登录用户可见）

---

## 7. 同步策略

### 6.1 同步顺序
1. **先同步 `shenwan_industry`**（行业分类定义）
2. **再同步 `shenwan_industry_member`**（成分股关联）

### 7.2 shenwan_industry 同步策略
| 项目 | 说明 |
|------|------|
| 频率 | 每年1-2次，手动触发或季度检查 |
| 方式 | 全量同步（数据量小，约500条）|
| 更新逻辑 | 新增直接插入；变更更新字段；删除标记 is_published=false |

### 7.3 shenwan_industry_member 同步策略
| 项目 | 说明 |
|------|------|
| 频率 | 每日或每周（成分股会调整）|
| 方式 | 增量同步（is_new='Y' 的数据）|
| 更新逻辑 | 见下方详细说明 |

#### 7.3.1 member 增量更新逻辑
```python
# 1. 拉取最新成分股
new_members = pro.index_member_all(is_new='Y')

# 2. 获取数据库中当前最新成分股
current_members = db.shenwan_industry_member.find({ is_new: 'Y' })

# 3. 对比处理
for each new_member in new_members:
    if new_member not in current_members:
        # 情况1：新增成分股
        insert with is_new='Y', in_date=今天
        
for each current_member not in new_members:
    # 情况2：被剔除的成分股
    update { is_new: 'N', out_date: 今天 }
```

### 7.4 数据验证
- **industry**: 验证层级关系完整性，编码规则
- **member**: 
  - 验证 is_new='Y' 的数据 out_date 必须为 null
  - 验证 is_new='N' 的数据 out_date 必须有值
  - 验证同一股票同一行业 in_date < out_date

---

## 8. 查询场景

### 8.1 行业相关查询
```javascript
// 获取2021版所有一级行业
db.shenwan_industry.find({ version: "2021", level: 1 })

// 获取某一级行业下的所有子行业
db.shenwan_industry.find({ version: "2021", level1_code: "110000" })
```

### 8.2 成分股查询
```javascript
// 获取某三级行业的所有最新成分股
db.shenwan_industry_member.find({ l3_code: "850531.SI", is_new: "Y" })

// 获取某一级行业的所有最新成分股
db.shenwan_industry_member.find({ l1_code: "801050.SI", is_new: "Y" })

// 获取某股票当前所属行业
db.shenwan_industry_member.find({ ts_code: "600547.SH", is_new: "Y" })

// 获取某股票历史行业变更记录
db.shenwan_industry_member.find({ ts_code: "600547.SH" }).sort({ in_date: -1 })

// 获取某行业的历史成分股（含已剔除的）
db.shenwan_industry_member.find({ l3_code: "850531.SI", is_new: "N" })
```

### 8.3 联合查询
```javascript
// 获取黄金行业详情及其成分股
var industry = db.shenwan_industry.findOne({ index_code: "850531.SI" })
var members = db.shenwan_industry_member.find({ l3_code: "850531.SI", is_new: "Y" })
```

---

## 9. API 调用提示

### 9.1 index_classify 调用
```python
import tushare as ts

pro = ts.pro_api("your_token")

# 分版本、分级别拉取
for version in ['SW2014', 'SW2021']:
    for level in ['L1', 'L2', 'L3']:
        df = pro.index_classify(src=version, level=level)
        # 处理并存储到 shenwan_industry
```

### 9.2 index_member_all 调用
```python
# 方式1：获取所有最新成分股（推荐）
df = pro.index_member_all(is_new='Y')

# 方式2：按三级行业查（用于验证）
df = pro.index_member_all(l3_code='850531.SI')

# 方式3：按股票查（用于单股查询）
df = pro.index_member_all(ts_code='600547.SH')
```

### 9.3 字段映射关系

#### index_classify 映射
| API 字段 | DB 字段 | 说明 |
|----------|---------|------|
| 行业代码 | industry_code | 直接使用 |
| 指数代码 | index_code | 直接使用 |
| 一级行业 | level1_name | 根据层级判断 |
| 二级行业 | level2_name | 根据层级判断 |
| 三级行业 | industry_name | 直接使用 |

#### index_member_all 映射
| API 字段 | DB 字段 | 说明 |
|----------|---------|------|
| l1_code | l1_code | 直接使用 |
| l1_name | l1_name | 直接使用 |
| l2_code | l2_code | 直接使用 |
| l2_name | l2_name | 直接使用 |
| l3_code | l3_code | 直接使用 |
| l3_name | l3_name | 直接使用 |
| ts_code | ts_code | 直接使用 |
| name | name | 直接使用 |
| in_date | in_date | 直接使用 |
| out_date | out_date | 空字符串转为 null |
| is_new | is_new | 直接使用 |

**注意**: API 返回的 l1/l2/l3_code 是指数代码（如 850531.SI），需与 shenwan_industry.index_code 关联

---

## 10. 待确认问题

开发前请与产品/用户确认：

1. **版本选择**: 默认使用 2021 版，是否需要同时支持两个版本切换？
2. **更新频率**: 
   - 行业分类定义：每年 1-2 次，手动触发？
   - 成分股：每日同步还是每周同步？
3. **历史记录**: 
   - 是否保留成分股剔除历史（is_new='N' 的数据）？
   - 保留多长时间？
4. **股票更名**: 当股票更名时（name 字段变化），是否更新历史记录？
5. **退市股票**: 退市股票的行业关联记录是否保留？

---

## 11. 开发检查清单

### 阶段1: 行业分类定义（后端）
- [x] 创建 `shenwan_industry` 集合
- [x] 创建索引（version+industry_code 唯一索引等）
- [x] 实现 `index_classify` 数据拉取脚本
- [x] 实现数据转换和存储逻辑

### 阶段2: 行业成分构成（后端）
- [x] 创建 `shenwan_industry_member` 集合
- [x] 创建索引（ts_code+l3_code+in_date 唯一索引等）
- [x] 实现 `index_member_all` 数据拉取脚本
- [x] 实现增量更新逻辑（识别新增/剔除的成分股）
- [x] 实现历史记录保留逻辑

### 阶段3: API 接口开发（后端）
- [x] 实现 `GET /sectors` - 获取一级行业列表（支持 version 参数）
- [x] 实现 `GET /sectors/{index_code}` - 获取行业详情及成分股
- [x] 实现 `GET /sectors/versions` - 获取支持的版本列表
- [x] 添加分页和筛选参数（is_new, page, page_size 等）

### 阶段4: 前端页面开发
- [x] 在顶部导航新增"板块"Tab（与"股票列表"并列）
- [x] 开发板块首页（/sectors）
  - [x] 一级行业卡片网格展示（显示名称、指数代码、成分股数）
  - [x] 版本切换功能（2021版/2014版）
  - [x] 点击进入详情页
- [x] 开发行业详情页（/sectors/{index_code}）
  - [x] 面包屑导航（一级 > 二级 > 三级，可点击跳转）
  - [x] 行业基本信息展示（名称、代码、成分股数、版本）
  - [x] 成分股列表展示（股票代码、名称、纳入日期、剔除日期、状态）
  - [x] "显示历史成分股"开关（默认只显示 is_new='Y'）
  - [x] 股票代码可点击跳转（携带 returnUrl 便于返回）
- [x] 在股票详情页新增"所属板块"卡片
  - [x] 展示该股票当前所属的一级/二级/三级行业
  - [x] 点击行业名称可跳转至对应板块详情页

### 阶段5: 测试与优化
- [x] 验证层级关系完整性
- [x] 验证 in_date/out_date 逻辑正确性
- [x] 验证增量更新逻辑正确性
- [ ] 验证页面跳转和返回逻辑
- [ ] 编写单元测试
