# 交易驱动持仓 · 前端 UX Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端把"交易驱动持仓"后端能力暴露给用户：新建资产时可选「按交易记录」或「手填」；derived 持仓只读展示（数量/成本由流水算出）+ 已实现盈亏 + 清仓折叠 + 卖超提示；总览展示总收益拆分；交易页文案与反馈更新。

**Architecture:** 沿用现有 React 18 + Vite + Ant Design 5 模式（无新依赖）。把分散在 `PlatformDetail.jsx` / `Platforms.jsx` 的持仓计算口径抽到一个纯函数模块 `src/holdings.js`（DRY，并加 derived/closed/anomaly 判定）。所有改动后端已就绪（Plan 1，23 测试全绿）。

**Tech Stack:** React 18 · Vite 5 · Ant Design 5 · ECharts · axios

**配套：** 设计文档 [docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md](../specs/2026-06-15-transaction-driven-holdings-design.md) §8；后端计划 [2026-06-15-transaction-driven-holdings-backend.md](2026-06-15-transaction-driven-holdings-backend.md)。

---

## 测试策略（重要，先读）

本项目前端**没有**单元测试框架（无 vitest/jest），现有约定就是无前端测试。为这几处 UI 改动引入 JS 测试栈属过度工程（YAGNI）。因此本计划每个任务的**自动门禁 = `npm run build` 必须通过**（能抓出语法/导入/JSX 错误），外加任务内列出的**手动验证清单**；最后 Task 7 做一次完整浏览器冒烟。`src/holdings.js` 抽成纯函数导出，便于将来真要加测试时直接测。

> 后端 API 已在 Plan 1 用 pytest 充分覆盖；前端这层是 UI 接线，build + 手动冒烟是与本项目规模相称的验证方式。

构建命令（从 `frontend/` 跑）：`cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
预期：`✓ built in ...`，无报错。

---

## File Structure

- **Create** `frontend/src/holdings.js` — 持仓显示纯函数：`marketValue` / `dayChange` / `costBasis` / `profitOf` + `isDerived` / `isClosed` / `isAnomalous`（消除 PlatformDetail 与 Platforms 的重复）
- **Modify** `frontend/src/constants.js` — 加 `HOLDING_SOURCES` / `HOLDING_SOURCE_LABEL`
- **Modify** `frontend/src/api/index.js` — `listHoldings` 已支持 params，无需改；确认即可
- **Modify** `frontend/src/pages/PlatformDetail.jsx` — 持仓表（derived 标记/已实现/清仓折叠/卖超/编辑删除护栏）+ 新建资产模式切换
- **Modify** `frontend/src/pages/Platforms.jsx` — 改用 `holdings.js`；展开行加 derived 标记（保持一致）
- **Modify** `frontend/src/pages/Transactions.jsx` — 文案改为"会驱动持仓" + 保存后反馈
- **Modify** `frontend/src/pages/Dashboard.jsx` — 顶部"累计盈亏"升级为"总收益"+ 悬浮拆分（未实现/已实现/分红）
- **Modify** `CHANGELOG.md` — 记录前端

每个任务自成一体，可独立 build 通过。

---

## Task 1: 抽取持仓显示纯函数模块（DRY 重构）

**Files:**
- Create: `frontend/src/holdings.js`
- Modify: `frontend/src/constants.js`
- Modify: `frontend/src/pages/PlatformDetail.jsx`
- Modify: `frontend/src/pages/Platforms.jsx`

- [ ] **Step 1: 创建 `frontend/src/holdings.js`**

```js
// 持仓显示口径（与后端 models.market_value / day_change / cost_basis / profit 对齐）。
// 纯函数，便于将来加测试。

export const marketValue = (h) =>
  h.manual_value != null ? h.manual_value
    : h.quantity != null && h.current_price != null ? h.quantity * h.current_price : 0

export const dayChange = (h) =>
  h.manual_value != null ? 0
    : h.quantity != null && h.current_price != null && h.prev_close != null
      ? h.quantity * (h.current_price - h.prev_close) : 0

export const costBasis = (h) =>
  (h.quantity != null && h.cost_price != null ? h.quantity * h.cost_price : null)

export const profitOf = (h) => {
  const cb = costBasis(h)
  return cb == null ? null : marketValue(h) - cb
}

// 交易驱动型（数量/成本由流水算出，前端只读）
export const isDerived = (h) => h.source === 'derived'
// 已清仓（数量归零）
export const isClosed = (h) => h.status === 'closed'
// 卖超异常（数量为负，提示用户检查流水）
export const isAnomalous = (h) => h.quantity != null && h.quantity < 0
```

- [ ] **Step 2: 在 `frontend/src/constants.js` 末尾加持仓来源枚举**

在 `TXN_ACTIONS` 的 `toMap` 区域附近（在 `export const TXN_ACTION_LABEL = toMap(TXN_ACTIONS)` 之后）加：
```js
export const HOLDING_SOURCES = [
  { value: 'manual', label: '手填' },
  { value: 'derived', label: '交易驱动' },
]
export const HOLDING_SOURCE_LABEL = toMap(HOLDING_SOURCES)
```

- [ ] **Step 3: 重构 `PlatformDetail.jsx` 改用 holdings.js**

删除文件顶部本地定义的 `marketValue` / `dayChange` / `costBasis` / `profitOf`（第 14–26 行那段），改为从模块导入。把 import 区域：
```js
import {
  CURRENCIES, ASSET_TYPES, MARKETS, MARKET_LABEL, ASSET_TYPE_LABEL, CURRENCY_SYMBOL, fmt,
} from '../constants'
```
其后新增一行：
```js
import { marketValue, dayChange, costBasis, profitOf } from '../holdings'
```
并删除那 4 个本地函数定义（确保文件内不再有重复定义）。其余逻辑不动。

- [ ] **Step 4: 重构 `Platforms.jsx` 改用 holdings.js**

同样删除 `Platforms.jsx` 顶部本地的 `marketValue` / `costBasis` / `profitOf`（第 12–20 行），import 区加：
```js
import { marketValue, costBasis, profitOf } from '../holdings'
```

- [ ] **Step 5: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误（导入解析正确、无重复声明）。

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/holdings.js frontend/src/constants.js frontend/src/pages/PlatformDetail.jsx frontend/src/pages/Platforms.jsx
git commit -m "refactor(frontend): extract holdings display helpers to src/holdings.js

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: PlatformDetail 持仓表 — derived 标记 / 已实现 / 清仓折叠 / 卖超 / 编辑删除护栏

**Files:**
- Modify: `frontend/src/pages/PlatformDetail.jsx`

- [ ] **Step 1: 引入新依赖与状态**

更新 import：
```js
import { marketValue, dayChange, costBasis, profitOf, isDerived, isClosed, isAnomalous } from '../holdings'
```
加图标 import（与现有 `@ant-design/icons` 合并）：
```js
import { PlusOutlined, ReloadOutlined, ArrowLeftOutlined, LinkOutlined, WarningOutlined } from '@ant-design/icons'
```
从 antd 增补 `Switch`、`Tooltip`（合并到现有 antd import 列表）。

在组件状态区（`const [refreshing, setRefreshing] = useState(false)` 之后）加：
```js
  const [showClosed, setShowClosed] = useState(false)
```

- [ ] **Step 2: load 时按 showClosed 传 include_closed**

把 `load` 里的 holdings 拉取改为带参数：
```js
      const [plats, holdings] = await Promise.all([
        listPlatforms(),
        listHoldings({ platform_id: platformId, include_closed: showClosed }),
      ])
```
并让 `useEffect` 依赖 `showClosed`：
```js
  useEffect(() => {
    load()
  }, [platformId, showClosed]) // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 3: 名称列加 derived 🔗 标记 / 已清仓 / 卖超提示**

把"名称"列的 `render` 替换为：
```js
      render: (t, r) => (
        <Space direction="vertical" size={0}>
          <Space size={4}>
            <span>{t || '（未命名）'}</span>
            {isDerived(r) && (
              <Tooltip title="由交易流水计算：数量/成本只读，请到「交易记录」增删流水">
                <Tag color="blue" icon={<LinkOutlined />} style={{ marginInlineStart: 0 }}>流水</Tag>
              </Tooltip>
            )}
            {isClosed(r) && <Tag>已清仓</Tag>}
            {isAnomalous(r) && (
              <Tooltip title="持仓数量为负，可能漏录了买入，请检查交易流水">
                <Tag color="warning" icon={<WarningOutlined />}>数量异常</Tag>
              </Tooltip>
            )}
          </Space>
          <span style={{ color: '#999', fontSize: 12 }}>{r.symbol}</span>
        </Space>
      ),
```

- [ ] **Step 4: 加"已实现"列（卖出结转 + 分红）**

在"盈亏"列之后、"操作"列之前插入新列：
```js
    {
      title: '已实现', align: 'right',
      render: (_, r) => {
        const realized = (r.realized_pnl || 0) + (r.realized_income || 0)
        if (!isDerived(r) || realized === 0) return '—'
        const up = realized >= 0
        return (
          <Tooltip title={`已实现盈亏 ${fmt(r.realized_pnl || 0)} + 分红 ${fmt(r.realized_income || 0)}`}>
            <span style={{ color: up ? '#cf1322' : '#3f8600' }}>
              {up ? '+' : ''}{CURRENCY_SYMBOL[r.currency] || ''}{fmt(realized)}
            </span>
          </Tooltip>
        )
      },
    },
```

- [ ] **Step 5: 操作列对 derived 持仓收敛（不能删；编辑入口提示去流水）**

把"操作"列 `render` 替换为：
```js
      render: (_, r) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          {isDerived(r) ? (
            <Tooltip title="该持仓由交易流水驱动，请在「交易记录」删除其流水">
              <span style={{ color: '#ccc', cursor: 'not-allowed' }}>删除</span>
            </Tooltip>
          ) : (
            <Popconfirm title="删除该资产？" onConfirm={() => remove(r.id)}>
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          )}
        </Space>
      ),
```

- [ ] **Step 6: 清仓行视觉淡化 + 顶部"显示已清仓"开关**

给 Table 加 `rowClassName`：
```js
      <Table rowKey="id" loading={loading} dataSource={data} columns={columns} pagination={false} scroll={{ x: 860 }}
        rowClassName={(r) => (isClosed(r) ? 'row-closed' : '')} />
```
在 Card 的 `extra` Space 内、"更新行情"按钮前加开关：
```js
          <Space size={4}>
            <span style={{ color: '#888', fontSize: 13 }}>显示已清仓</span>
            <Switch size="small" checked={showClosed} onChange={setShowClosed} />
          </Space>
```
并在文件中给清仓行加淡化样式 —— 在组件 `return` 的最外层 `Card` 之上不便插 CSS，改为在 `frontend/src/index.css`（若不存在则在 `main.jsx` 引入的全局样式文件）追加。先确认全局样式文件：Run `ls frontend/src/*.css 2>/dev/null; grep -rn "import .*css" frontend/src/main.jsx`。把以下规则追加到已被引入的那个全局 css 文件（如 `frontend/src/index.css`）：
```css
.row-closed td { opacity: 0.55; }
```
若项目没有任何全局 css 被引入，则跳过该 css（行淡化非必须），保留"已清仓"Tag 即可——在 commit 说明里注明。

- [ ] **Step 7: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误。

- [ ] **Step 8: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/pages/PlatformDetail.jsx frontend/src/index.css 2>/dev/null; git add frontend/src/pages/PlatformDetail.jsx
git commit -m "feat(frontend): derived holding markers, realized column, closed toggle & guards

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: PlatformDetail 新建资产 — 「按交易记录」/「直接手填」模式切换

**Files:**
- Modify: `frontend/src/pages/PlatformDetail.jsx`

- [ ] **Step 1: 引入交易接口与日期组件**

import 增补：
```js
import { DatePicker, Segmented } from 'antd' // 合并进现有 antd import
import dayjs from 'dayjs'
import { createTransaction } from '../api' // 合并进现有 ../api import
```
新增状态（在 `editing` 状态附近）：
```js
  const [mode, setMode] = useState('derived') // 新建模式：derived(按交易) / manual(手填)
```

- [ ] **Step 2: openAdd 重置模式；编辑时按 source 锁定**

把 `openAdd` 改为：
```js
  const openAdd = () => {
    setEditing(null)
    setMode('derived')
    form.resetFields()
    form.setFieldsValue({ currency: 'CNY', asset_type: 'stock', market: 'A', date: dayjs() })
    setOpen(true)
  }
```
把 `openEdit` 改为（编辑 derived 时，数量/成本不可改，模式锁为该持仓来源）：
```js
  const openEdit = (r) => {
    setEditing(r)
    setMode(r.source === 'derived' ? 'derived-edit' : 'manual')
    form.setFieldsValue(r)
    setOpen(true)
  }
```

- [ ] **Step 3: submit 按模式分流**

把 `submit` 替换为：
```js
  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        // 编辑：derived 只改可改字段（name/asset_type/market），数量/成本由流水定
        const patch = editing.source === 'derived'
          ? { name: values.name, asset_type: values.asset_type, market: values.market }
          : values
        await updateHolding(editing.id, patch)
      } else if (mode === 'derived') {
        // 按交易记录：记一笔买入，后端自动建/更新 derived 持仓
        await createTransaction({
          platform_id: platformId, action: 'buy',
          date: values.date ? values.date.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD'),
          name: values.name, symbol: values.symbol, currency: values.currency,
          quantity: values.quantity, price: values.price, fee: values.fee,
        })
      } else {
        await createHolding({ ...values, platform_id: platformId, source: 'manual' })
      }
      message.success('已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    }
  }
```

- [ ] **Step 4: Modal 内按模式渲染不同表单**

在 Modal 的 `<Form>` 顶部加模式切换（仅新建时显示）：
```js
          {!editing && (
            <Segmented
              block
              value={mode}
              onChange={setMode}
              style={{ marginBottom: 16 }}
              options={[
                { label: '按交易记录（推荐）', value: 'derived' },
                { label: '直接手填', value: 'manual' },
              ]}
            />
          )}
```
然后把"持有数量/成本价/手填市值"那一组 `Space`（第 218–228 行）替换为按模式分支：
```js
          {(mode === 'derived' && !editing) ? (
            <Space style={{ display: 'flex' }}>
              <Form.Item name="date" label="买入日期" rules={[{ required: true }]} style={{ flex: 1 }}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="quantity" label="买入数量" rules={[{ required: true }]} style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="股数/份额" />
              </Form.Item>
              <Form.Item name="price" label="买入价" rules={[{ required: true }]} style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="成交价" />
              </Form.Item>
              <Form.Item name="fee" label="费用" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="手续费" />
              </Form.Item>
            </Space>
          ) : (
            <Space style={{ display: 'flex' }}>
              <Form.Item name="quantity" label="持有数量/份额" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="股数/份额" disabled={editing?.source === 'derived'} />
              </Form.Item>
              <Form.Item name="cost_price" label="成本价（可选）" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="用于盈亏" disabled={editing?.source === 'derived'} />
              </Form.Item>
              <Form.Item name="manual_value" label="手填市值（无法抓价时）" style={{ flex: 1.2 }}>
                <InputNumber style={{ width: '100%' }} placeholder="现金/债券等直接填金额" disabled={editing?.source === 'derived'} />
              </Form.Item>
            </Space>
          )}
```
并在编辑 derived 时给出提示——在上面分支的下方加：
```js
          {editing?.source === 'derived' && (
            <div style={{ color: '#888', fontSize: 12, marginTop: -8 }}>
              数量与成本由交易流水自动计算，如需调整请到「交易记录」增删对应流水。
            </div>
          )}
```

- [ ] **Step 5: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误。

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/pages/PlatformDetail.jsx
git commit -m "feat(frontend): add-asset mode toggle (transaction-driven vs manual)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 交易页文案与反馈更新

**Files:**
- Modify: `frontend/src/pages/Transactions.jsx`

- [ ] **Step 1: 更新顶部说明文案**

把第 144–146 行的提示：
```js
      <div style={{ marginBottom: 12, color: '#888', fontSize: 13 }}>
        独立流水账本，仅作记录，不会自动改变你的持仓。
      </div>
```
替换为：
```js
      <div style={{ marginBottom: 12, color: '#888', fontSize: 13 }}>
        买入/卖出会自动更新对应持仓（按 平台 + 代码 + 币种 匹配）的数量与移动加权成本；
        分红计入已实现收益。入金/出金/其它仅作记录。
      </div>
```

- [ ] **Step 2: 保存后反馈提示持仓已同步**

把 `submit` 里成功分支的 `message.success('已保存')` 替换为：
```js
      const drives = ['buy', 'sell', 'dividend'].includes(payload.action)
      message.success(drives ? '已保存，相关持仓已同步' : '已保存')
```

- [ ] **Step 3: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误。

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/pages/Transactions.jsx
git commit -m "feat(frontend): transactions copy + post-save sync feedback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 总览顶部「总收益」+ 悬浮拆分

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: 计算总收益与各分量**

在 `const totalProfit = summary?.total_profit ?? 0` 附近（约第 69 行）加：
```js
  const realizedPnl = summary?.realized_pnl ?? 0
  const realizedIncome = summary?.realized_income ?? 0
  const totalReturn = summary?.total_return ?? totalProfit
  const returnUp = totalReturn >= 0
  const returnColor = returnUp ? RED : GREEN
```

- [ ] **Step 2: 顶部"累计盈亏"块升级为"总收益"+ 悬浮明细**

把现有"累计盈亏"那段 `<Space size={4}>...累计盈亏...</Space>`（约第 124–132 行）替换为：
```js
                <Space size={4}>
                  <span style={{ color: returnColor, fontSize: 16 }}>
                    {returnUp ? '+' : ''}{sym}{fmt(totalReturn)}
                  </span>
                  <Tooltip
                    title={(
                      <div>
                        <div>未实现盈亏：{returnUp ? '' : ''}{sym}{fmt(totalProfit)}</div>
                        <div>已实现盈亏：{sym}{fmt(realizedPnl)}</div>
                        <div>分红/利息：{sym}{fmt(realizedIncome)}</div>
                        <div style={{ color: '#aaa', marginTop: 4 }}>总收益 = 三项之和</div>
                      </div>
                    )}
                  >
                    <span style={{ color: '#aaa' }}>总收益 ⓘ</span>
                  </Tooltip>
                </Space>
```

> 注：保留"今日"那块不变；隐私模式下 `fmt` 已自动打码，Tooltip 内也走 `fmt` 因此一致打码。

- [ ] **Step 3: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误。

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat(frontend): dashboard total-return with unrealized/realized/dividend breakdown

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Platforms 展开行一致性（derived 标记）

**Files:**
- Modify: `frontend/src/pages/Platforms.jsx`

- [ ] **Step 1: 引入判定 + 图标**

import 增补：
```js
import { isDerived } from '../holdings' // 合并进 Task 1 已加的 ../holdings import
import { PlusOutlined } from '@ant-design/icons' // 已有；再加 LinkOutlined
```
即把图标 import 改为 `import { PlusOutlined, LinkOutlined } from '@ant-design/icons'`。

- [ ] **Step 2: 展开行名称列加 🔗 标记**

把 `expandedRowRender` 里 `subColumns` 的"名称"列 `render` 替换为：
```js
        render: (t, r) => (
          <Space direction="vertical" size={0}>
            <Space size={4}>
              <span>{t || '（未命名）'}</span>
              {isDerived(r) && <Tag color="blue" icon={<LinkOutlined />} style={{ marginInlineStart: 0 }}>流水</Tag>}
            </Space>
            <span style={{ color: '#999', fontSize: 12 }}>
              {[ASSET_TYPE_LABEL[r.asset_type], r.symbol].filter(Boolean).join(' · ')}
            </span>
          </Space>
        ),
```
（`Tag` 已在 antd import 中；若没有则补上。）

> 平台页 `listHoldings()` 不传 `include_closed`，后端默认隐藏清仓持仓 —— 平台总额自然不含已清仓，符合预期，无需改。

- [ ] **Step 3: 构建验证**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built` 无错误。

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add frontend/src/pages/Platforms.jsx
git commit -m "feat(frontend): mark derived holdings in platform expanded rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 完整构建 + 浏览器手动冒烟 + 文档

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 生产构建通过**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem/frontend" && npm run build`
Expected: `✓ built`，无报错、无未使用变量导致的失败。

- [ ] **Step 2: 浏览器手动冒烟（控制者/用户执行）**

启动：`cd "/Volumes/T7 Shield/Study/CS/FinancialSystem" && python3 dev.py start`，登录后逐项验证：
1. 进某平台 → 添加资产 → 默认「按交易记录」→ 填日期/数量/价格买入 → 列表出现该持仓，带蓝色「流水」🔗 标记，数量/成本与买入一致。
2. 再去「交易记录」给同一标的记一笔买入（同平台+代码+币种）→ 回平台详情，数量/成本按移动加权更新。
3. 编辑该 derived 持仓 → 数量/成本输入框禁用，有"请到交易记录修改"提示；删除显示为不可点（灰）。
4. 记一笔卖出清掉全部 → 默认列表不显示该持仓；打开「显示已清仓」开关 → 出现并标「已清仓」，"已实现"列有数字。
5. 卖超（卖出多于持有）→ 该持仓出现「数量异常」⚠️。
6. 总览顶部「总收益 ⓘ」悬浮 → 显示 未实现/已实现/分红 三行拆分。
7. 「直接手填」模式仍可加现金/债券类手填资产，行为如旧。
8. 隐私模式开启 → 上述金额（含已实现列、总收益悬浮）均打码为 ****。

记录任何不符，若发现 bug：停下来修（回到对应任务）。

- [ ] **Step 3: 更新 `CHANGELOG.md`**

在记录区顶部加：
```
## [新增] - 2026-06-16 交易驱动持仓（前端 UX · Plan 2）
### 类型：✨新增
- **改了什么**：新建资产支持「按交易记录」（记一笔买入自动建 derived 持仓）/「直接手填」两种模式；derived 持仓数量/成本只读并标「流水」🔗、编辑禁用、不可直接删除；持仓表新增「已实现」列、清仓持仓默认隐藏（开关可显示并标「已清仓」）、卖超显示「数量异常」；总览顶部「累计盈亏」升级为「总收益」并悬浮拆分 未实现/已实现/分红；交易页文案改为说明会驱动持仓、保存后提示已同步。
- **为什么**：把 Plan 1 的后端能力暴露给用户，让"交易→持仓"闭环可用。
- **影响范围**：前端 新增 `src/holdings.js`；`constants.js`、`pages/PlatformDetail.jsx`、`pages/Platforms.jsx`、`pages/Transactions.jsx`、`pages/Dashboard.jsx`。
- **注意事项**：无后端改动；无新依赖。前端无单测框架，验证为 `npm run build` + 浏览器手动冒烟。
```

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add CHANGELOG.md
git commit -m "docs: record transaction-driven holdings frontend (Plan 2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 完成标准

- `npm run build` 通过（无错误）。
- 新建资产可选「按交易记录」/「手填」；交易买卖自动驱动 derived 持仓数量/成本。
- derived 持仓只读（编辑禁用数量/成本、不可删）并有 🔗 标记；清仓默认隐藏、可开关；卖超有异常标记；"已实现"列正确。
- 总览展示「总收益」及未实现/已实现/分红拆分。
- 手填资产（现金/债券）行为不变；隐私模式打码一致。
- 浏览器冒烟 8 项全过。
