# Parquet 存储方案使用说明

## 概述

为了解决 DuckDB 单文件过大的问题，我们实现了 **Parquet 文件 + DuckDB 视图** 的混合存储方案：

- **原始数据**：存储在 Parquet 文件中（按日期分区）
- **DuckDB**：只存储元数据（策略、回测记录等）和 Parquet 视图
- **查询**：DuckDB 直接读取 Parquet 文件，无需导入

## 目录结构

迁移后的目录结构：

```
data/
  raw/
    daily/
      trade_date=20240101/
        part-0.parquet
      trade_date=20240102/
        part-0.parquet
      ...
    adj_factor/
      trade_date=20240101/
        part-0.parquet
      ...
    stock_basic/
      part-0.parquet
  quant.duckdb  # 只存储元数据（策略、回测记录等）
```

## 使用方法

### 1. 迁移现有数据

如果已有 DuckDB 数据，运行迁移脚本：

```bash
cd backend
python scripts/migrate_to_parquet.py
```

迁移脚本会：
- 将 `daily` 表数据按日期分区写入 Parquet
- 将 `adj_factor` 表数据按日期分区写入 Parquet
- 将 `stock_basic` 表数据写入 Parquet

### 2. 新数据自动写入 Parquet

迁移完成后，新的数据拉取会自动：
- 写入 Parquet 文件（按日期分区）
- DuckDB 通过视图自动读取 Parquet 数据

### 3. 查询无需修改

所有现有的查询代码无需修改，因为：
- DuckDB 视图提供了与表相同的接口
- `list_daily()`, `get_daily_with_adj()` 等函数正常工作

## 优势

1. **文件大小可控**：每个 Parquet 文件较小（按日期分区）
2. **查询性能**：DuckDB 可直接查询 Parquet，性能优秀
3. **易于备份**：可按日期备份/删除历史数据
4. **向后兼容**：现有代码无需修改

## 注意事项

1. **首次查询可能稍慢**：DuckDB 需要读取 Parquet 元数据
2. **Parquet 文件需要存在**：如果 Parquet 文件不存在，会回退到 DuckDB 表
3. **迁移后保留原表**：DuckDB 中的原表仍然保留（作为备份），确认 Parquet 数据正确后可删除

## 清理旧数据

如果需要清理旧的 Parquet 文件（例如删除某个日期之前的数据）：

```bash
# 删除 2024-01-01 之前的数据
rm -rf data/raw/daily/trade_date=20240101
rm -rf data/raw/adj_factor/trade_date=20240101
```

## 故障排查

### 问题：查询返回空数据

**可能原因**：
- Parquet 文件不存在
- 视图注册失败

**解决方法**：
1. 检查 Parquet 文件是否存在：`ls -la data/raw/daily/`
2. 重新运行迁移脚本
3. 检查 DuckDB 日志

### 问题：迁移失败

**可能原因**：
- DuckDB 文件损坏
- 磁盘空间不足

**解决方法**：
1. 备份现有数据
2. 检查磁盘空间：`df -h`
3. 尝试分批迁移（修改 `batch_size` 参数）

## 性能优化建议

1. **定期清理旧数据**：删除不需要的历史 Parquet 文件
2. **使用压缩**：Parquet 文件已自动压缩
3. **批量查询**：尽量使用日期范围查询，利用分区优势

