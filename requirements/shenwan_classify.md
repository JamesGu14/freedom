# 申万行业分类数据存储需求文档

## 1. 背景与目标

### 1.1 数据源
- **API 接口**: Tushare `index_classify`
- **接口描述**: 获取申万行业分类数据
- **权限要求**: 需 2000 积分
- **数据版本**: 
  - 2014版：28个一级分类，104个二级分类，227个三级分类
  - 2021版：31个一级分类，134个二级分类，346个三级分类

### 1.2 业务目标
- 存储申万行业分类的层级结构数据
- 支持股票与行业分类的关联查询
- 支持历史版本追溯（2014版 vs 2021版）

---

## 2. API 数据字段说明

### 2.1 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| src | str | N | 来源（如 SW2021 表示 2021 版）|
| level | str | N | 行业等级（L1/L2/L3）|

### 2.2 返回字段
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

---

## 3. 数据库选型

### 3.1 选型决策
**选择 MongoDB**

**理由**:
1. **与现有架构一致**: 项目已使用 MongoDB 存储业务数据（daily_signal, stock_basic 等）
2. **数据结构灵活**: 行业分类数据为树状层级结构，MongoDB 的文档模型更适合存储
3. **查询需求**: 主要按版本、层级、父节点查询，MongoDB 索引支持良好
4. **数据量适中**: 两个版本总共约 500+ 条记录，无需 DuckDB 的列式存储优势

---

## 4. 表结构设计

### 4.1 集合（Collection）设计

#### 集合名称
`shenwan_industry`

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
  "level1_code": "110000",             // 一级行业代码（冗余，便于快速筛选）
  "level1_name": "农林牧渔",            // 一级行业名称
  "level2_code": "110100",             // 二级行业代码（一级、二级为 null）
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

### 4.2 索引设计

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

// 查询索引：父级代码
db.shenwan_industry.createIndex(
  { "parent_code": 1 },
  { name: "idx_parent_code" }
)

// 查询索引：是否发布（用于过滤不发布的行业）
db.shenwan_industry.createIndex(
  { "is_published": 1 },
  { name: "idx_published" }
)
```

### 4.3 数据示例

#### 一级行业
```javascript
{
  "industry_code": "110000",
  "index_code": "801010",
  "industry_name": "农林牧渔",
  "level": 1,
  "level_name": "一级行业",
  "parent_code": null,
  "level1_code": "110000",
  "level1_name": "农林牧渔",
  "level2_code": null,
  "level2_name": null,
  "version": "2021",
  "version_note": "2021保留",
  "is_published": true,
  "constituent_count": 100
}
```

#### 二级行业
```javascript
{
  "industry_code": "110100",
  "index_code": "801016",
  "industry_name": "种植业",
  "level": 2,
  "level_name": "二级行业",
  "parent_code": "110000",
  "level1_code": "110000",
  "level1_name": "农林牧渔",
  "level2_code": "110100",
  "level2_name": "种植业",
  "version": "2021",
  "version_note": "2021保留",
  "is_published": true,
  "constituent_count": 20
}
```

#### 三级行业
```javascript
{
  "industry_code": "110101",
  "index_code": "850111",
  "industry_name": "种子",
  "level": 3,
  "level_name": "三级行业",
  "parent_code": "110100",
  "level1_code": "110000",
  "level1_name": "农林牧渔",
  "level2_code": "110100",
  "level2_name": "种植业",
  "version": "2021",
  "version_note": "2021改名",
  "is_published": true,
  "constituent_count": 8
}
```

---

## 5. 关联设计

### 5.1 股票与行业关联
**建议不在 `shenwan_industry` 中存储成分股列表**（因为成分股会变化，且数据量大）

**关联方式**:
- 方式1：在 `stock_basic` 集合中增加 `shenwan_industry_code` 字段
- 方式2：创建独立的 `stock_industry_mapping` 集合存储股票与行业的关系

**推荐方式1**（简单场景）:
```javascript
// stock_basic 文档增加字段
{
  "ts_code": "000001.SZ",
  "name": "平安银行",
  "industry": "银行",                    // 原有行业
  "shenwan_code_2021": "510300"         // 申万行业代码（2021版）
  "shenwan_code_2014": "510300"         // 申万行业代码（2014版）
}
```

---

## 6. 同步策略

### 6.1 同步频率
- **初次**: 全量拉取两个版本（2014、2021）
- **后续**: 申万行业分类调整频率低（每年 1-2 次），可手动触发或季度同步

### 6.2 同步逻辑提示
1. **版本控制**: API 支持 `src` 参数（SW2014/SW2021），分别调用两次
2. **层级拉取**: 建议分三次拉取（L1/L2/L3），便于数据处理
3. **去重策略**: 使用 `industry_code` + `version` 作为唯一键
4. **更新策略**: 
   - 新增：直接插入
   - 变更（改名/合并）：更新 `industry_name` 和 `version_note`
   - 删除（极少）：标记 `is_published: false`

### 6.3 数据验证
- 验证层级关系完整性（每个非一级行业必须有父级）
- 验证编码规则（一级以 0000 结尾，二级以 00 结尾但不是 0000）
- 验证成分股数量 >= 0

---

## 7. 查询场景

### 7.1 常见查询
```javascript
// 获取2021版所有一级行业
db.shenwan_industry.find({ version: "2021", level: 1, is_published: true })

// 获取某一级行业下的所有二级、三级行业
db.shenwan_industry.find({ version: "2021", level1_code: "110000" })

// 获取某二级行业下的三级行业
db.shenwan_industry.find({ version: "2021", parent_code: "110100" })

// 获取发布的行业（过滤成分股数<5的不发布行业）
db.shenwan_industry.find({ version: "2021", is_published: true })
```

---

## 8. API 调用提示

### 8.1 调用示例
```python
import tushare as ts

pro = ts.pro_api("your_token")

# 拉取2021版一级行业
df_l1 = pro.index_classify(src='SW2021', level='L1')

# 拉取2021版二级行业
df_l2 = pro.index_classify(src='SW2021', level='L2')

# 拉取2021版三级行业
df_l3 = pro.index_classify(src='SW2021', level='L3')
```

### 8.2 字段映射
| API 返回字段 | 数据库字段 | 说明 |
|--------------|------------|------|
| 行业代码 | industry_code | 直接使用 |
| 指数代码 | index_code | 直接使用 |
| 一级行业 | level1_name | 根据层级判断存入哪个字段 |
| 二级行业 | level2_name / industry_name | 根据层级判断 |
| 三级行业 | industry_name | 直接使用 |
| 指数类别 | level | 转换为数字（1/2/3） |
| 是否发布 | is_published | 转换为布尔值 |
| 变动原因 | version_note | 直接使用 |
| 成分股数 | constituent_count | 转换为整数 |

### 8.3 层级判断逻辑
- **L1 数据**: `industry_name` = `level1_name`
- **L2 数据**: `industry_name` = `level2_name`, `parent_code` = `level1_code`
- **L3 数据**: `industry_name` = `level3_name`, `parent_code` = `level2_code`

---

## 9. 待确认问题

开发前请与产品/用户确认：

1. **版本选择**: 默认使用 2021 版，是否需要同时支持两个版本切换？
2. **股票关联**: 股票是否需要关联到最细粒度的三级行业，还是关联到一级/二级即可？
3. **历史追溯**: 是否需要记录行业变更历史（如股票从A行业调整到B行业）？
4. **不发布行业**: 成分股数<5的行业（is_published=0）是否需要存储？
5. **更新频率**: 是否需要定时自动同步，还是手动触发即可？

---

## 10. 开发检查清单

- [ ] 创建 `shenwan_industry` 集合
- [ ] 创建所需索引
- [ ] 实现 API 数据拉取脚本
- [ ] 实现数据转换和存储逻辑
- [ ] 实现层级关系验证
- [ ] 实现增量更新逻辑（可选）
- [ ] 添加异常处理和日志
- [ ] 编写单元测试
