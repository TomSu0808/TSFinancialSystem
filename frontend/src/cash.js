// 现金账本语义（与 backend/cash_service.py 保持一致，避免前端重复计费/口径不一致）。
// 纯函数，供交易表单、现金区复用。

// buy/sell 净现金流（正数）：手填 amount 为实际收付净额，否则 量×价 ± 费。
export const tradeNet = (t) => {
  if (t.amount != null) return t.amount
  const gross = (t.quantity || 0) * (t.price || 0)
  const fee = t.fee || 0
  return t.action === 'buy' ? gross + fee : gross - fee
}

// deposit/withdraw/dividend/cash_adjust 的金额：优先 amount，其次 quantity（缺失/非正时回退）。
export const explicitAmount = (t) => {
  const amt = t.amount
  if (amt == null || amt <= 0) return t.quantity || 0
  return amt
}

// 带符号现金流；无现金流的动作返回 null。cash_adjust 是绝对余额（非增量），返回 null。
export const cashFlow = (t) => {
  switch (t.action) {
    case 'deposit': return explicitAmount(t)
    case 'withdraw': return -explicitAmount(t)
    case 'dividend': return explicitAmount(t)
    case 'buy': return -tradeNet(t)
    case 'sell': return tradeNet(t)
    default: return null // cash_adjust / adjust / other
  }
}

// 预计交易后余额：已初始化时返回 currentBalance + flow；未初始化/无增量返回 null。
export const projectedBalance = (currentBalance, flow) =>
  (currentBalance == null || flow == null) ? null : currentBalance + flow

// 按 (platform_id, symbol, currency) 精确匹配唯一持仓；未匹配返回 null。
export const findHolding = (holdings, platformId, symbol, currency) => {
  if (platformId == null || !symbol) return null
  const sym = (symbol || '').trim()
  return (holdings || []).find(
    (h) => h.asset_type !== 'cash'
      && h.platform_id === platformId
      && (h.symbol || '').trim() === sym
      && h.currency === currency,
  ) || null
}

// 持仓数量状态：'insufficient' 信息不足 / 'none' 未匹配（新标的）/ 'unknown' 数量未知 / 'known' 已知。
export const holdingStatus = (holdings, { platform_id, symbol, currency }) => {
  if (platform_id == null || !(symbol || '').trim()) return { kind: 'insufficient' }
  const h = findHolding(holdings, platform_id, symbol, currency)
  if (!h) return { kind: 'none' }
  if (h.quantity == null) return { kind: 'unknown', holding: h }
  return { kind: 'known', quantity: h.quantity, holding: h }
}

// 预计交易后数量：仅当当前数量已知且输入数量有效时返回数字，否则 null。
export const projectedQuantity = (action, currentQty, qty) => {
  if (currentQty == null || qty == null) return null
  if (action === 'buy') return currentQty + qty
  if (action === 'sell') return currentQty - qty
  return null
}
