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
