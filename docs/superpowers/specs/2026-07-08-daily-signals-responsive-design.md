# Daily Signals / 首页共振面板响应式美化设计文档

> 日期: 2026-07-08
> 项目: Freedom Quant Platform
> 作者: AI Assistant

---

## 1. 需求概述

美化首页（`/`）的"买入共振 / 卖出共振"和"买入信号 / 卖出信号"股票面板，重点解决 27 寸等大屏幕下股票卡片一行显示 8 个、名称和代码拥挤难读的问题。

**明确不在本次范围内**：`/daily-signals.js` 表格页面保持现状，本次只改首页的卡片网格。

### 1.1 用户故事

- 作为交易者，我想在大屏幕上清晰看到每只股票的名字、代码和得分，以便快速识别机会
- 作为交易者，我希望页面在不同屏幕尺寸下都能保持良好的阅读体验

### 1.2 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 响应式股票网格 | P0 | 大屏 5 列，随屏幕宽度递减 |
| 卡片美化 | P0 | 增加内边距、hover 高亮、视觉层次 |
| 暗色主题兼容 | P0 | 保持与现有 dark/light 变量一致 |

---

## 2. 设计方案

### 2.1 响应式列数

首页的 `.signal-stock-grid` 当前是固定的 `repeat(8, 1fr)`，会导致大屏幕上卡片过窄。为避免影响其他使用 `.signal-stock-grid` 的组件（如 `SignalGroupPopup` 弹窗），给首页的网格增加 modifier 类 `.signal-stock-grid--resonance`，仅对该 modifier 应用响应式列数：

| 屏幕宽度 | 列数 |
|----------|------|
| ≥ 1600px | 5 列 |
| 1200px - 1599px | 4 列 |
| 768px - 1199px | 3 列 |
| < 768px | 2 列 |

### 2.2 卡片美化

针对 `.signal-stock-grid--resonance .signal-stock-cell`：

- 内边距从 `6px 8px` 增加到 `10px 12px`
- gap 从 `6px` 增加到 `10px`
- hover 状态：
  - 边框：`border-color: var(--border)`
  - 背景：`background: var(--bg-subtle)`
  - 过渡：`transition: border-color 0.15s, background 0.15s`
- 名称字号保持 12px，代码和辅助信息保持 10px
- 保持 `min-width: 0` 和文字截断，避免布局撑破

### 2.3 长名字处理

当卡片宽度不足以水平显示"名字 + 代码"时，允许代码换行或截断：

- `.signal-stock-cell__head` 保持 `flex` 布局
- `.signal-stock-cell__name` 保持 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`
- `.signal-stock-cell__code` 允许收缩，避免撑破容器
- 在 3 列/2 列的小屏幕上，如果空间仍不足，代码自动隐藏或换行（由 flex-wrap 控制）

### 2.4 高亮样式兼容

- `.signal-stock-cell--acknowledged` 的橙色边框和背景保持最高优先级，hover 时不覆盖其边框色
- hover 只改变背景为 `var(--bg-subtle)`，不覆盖 acknowledged 的背景

### 2.5 涉及的文件

- `frontend/pages/index.js`：给首页的 `StockList` 渲染网格增加 `.signal-stock-grid--resonance` 类
- `frontend/styles/globals.css`：新增 `.signal-stock-grid--resonance` 响应式样式，微调 `.signal-stock-cell` hover 状态

---

## 3. 测试计划

1. 在 2560×1440（27 寸）宽度下确认一行 5 个卡片，文字清晰
2. 在 1920×1080 宽度下确认一行 5 个卡片
3. 在 1366px 宽度下确认一行 4 个卡片
4. 在 iPad 宽度（768px-1024px）下确认一行 3 个卡片
5. 在手机宽度（< 768px）下确认一行 2 个卡片
6. 验证暗色/亮色主题切换后样式正常
7. 验证 `SignalGroupPopup` 弹窗内的股票网格不受影响（仍保持原有 8 列或弹窗自有样式）
8. 验证 acknowledged 股票的高亮样式与 hover 样式不冲突

---

## 4. 回滚计划

- 若线上样式异常，直接回滚 `frontend/styles/globals.css` 和 `frontend/pages/index.js` 的修改
- 重新构建并部署前端镜像

---

## 5. 遗漏项确认

- [x] 范围限定为首页（`/`）的共振/信号面板
- [x] 使用 modifier 类避免影响弹窗
- [x] 给出具体的 padding、gap、hover 颜色值
- [x] 考虑长名字和代码的截断/换行
- [x] 考虑 acknowledged 高亮样式与 hover 的优先级
- [x] 明确测试断点和构建验证
- [x] 提供回滚计划

---

*文档版本: 1.1*
