# 首页共振面板响应式美化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution.

**Goal:** 将首页（`/`）的股票卡片网格从固定 8 列改为响应式 5/4/3/2 列，并美化卡片样式。

**Architecture:** 通过给首页 `StockList` 增加 modifier 类 `.signal-stock-grid--resonance`，仅对首页应用响应式列数；保持弹窗内网格不变。在 `globals.css` 中新增媒体查询和 hover 样式。

**Tech Stack:** Next.js 14, CSS custom properties, existing dark/light theme tokens

---

### Task 1: 给首页 StockList 增加 modifier 类

**Files:**
- Modify: `frontend/pages/index.js:432`

- [ ] **Step 1: 修改 StockList 组件的网格容器类名**

当前代码：
```jsx
<div className="signal-stock-grid">
```

改为：
```jsx
<div className="signal-stock-grid signal-stock-grid--resonance">
```

- [ ] **Step 2: 构建验证**

Run: `cd frontend && npm run build`
Expected: Compiled successfully

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/index.js
git commit -m "refactor: add signal-stock-grid--resonance modifier for homepage"
```

---

### Task 2: 添加响应式网格和卡片美化样式

**Files:**
- Modify: `frontend/styles/globals.css:825-900` 附近

- [ ] **Step 1: 修改基础网格和卡片样式**

保留 `.signal-stock-grid` 默认样式不变（弹窗仍使用）：
```css
.signal-stock-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 6px;
}
```

新增 `.signal-stock-grid--resonance`：
```css
.signal-stock-grid--resonance {
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.signal-stock-grid--resonance .signal-stock-cell {
  padding: 10px 12px;
}

.signal-stock-grid--resonance .signal-stock-cell:hover {
  background: var(--bg-subtle);
  border-color: var(--border);
}

.signal-stock-grid--resonance .signal-stock-cell--acknowledged:hover {
  background: rgba(245, 158, 11, 0.05);
}
```

- [ ] **Step 2: 添加响应式媒体查询**

在 `globals.css` 的媒体查询区域（约 946 行附近）新增：
```css
@media (max-width: 1599px) {
  .signal-stock-grid--resonance {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 1199px) {
  .signal-stock-grid--resonance {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 767px) {
  .signal-stock-grid--resonance {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .signal-stock-grid--resonance .signal-stock-cell {
    padding: 8px 10px;
  }
}
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: Compiled successfully

- [ ] **Step 4: 截图验证**

Run headless browser screenshots at widths: 1920, 1366, 768, 375
Expected: card grid shows 5/4/3/2 columns respectively; text readable

- [ ] **Step 5: Commit**

```bash
git add frontend/styles/globals.css
git commit -m "feat: responsive 5-col grid and card hover for homepage resonance panels"
```

---

### Task 3: 部署

**Files:**
- N/A (docker compose rebuild)

- [ ] **Step 1: 重新构建并部署**

Run: `docker compose -f docker-compose.yaml up --build -d`
Expected: frontend and backend containers recreated successfully

- [ ] **Step 2: 验证容器状态**

Run: `docker compose -f docker-compose.yaml ps`
Expected: freedom-frontend-1 Up, freedom-backend-1 Up

---

## Spec Coverage Check

- [x] 响应式 5/4/3/2 列 → Task 2 Step 2
- [x] 卡片内边距加大 → Task 2 Step 1
- [x] hover 高亮 → Task 2 Step 1
- [x] 暗色/亮色兼容 → uses CSS variables
- [x] 不影响弹窗网格 → Task 1 (modifier class)
- [x] acknowledged 样式优先级 → Task 2 Step 1
- [x] 测试计划 → Task 2 Step 4
- [x] 回滚计划 → revert two commits
