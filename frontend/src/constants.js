// 枚举的中文标签与下拉选项，前后端 value 保持一致

export const CURRENCIES = [
  { value: 'CNY', label: '人民币 ¥' },
  { value: 'USD', label: '美元 $' },
  { value: 'HKD', label: '港币 HK$' },
]

export const ASSET_TYPES = [
  { value: 'stock', label: '股票' },
  { value: 'etf', label: '场内基金/ETF' },
  { value: 'fund', label: '场外基金' },
  { value: 'bond', label: '债券' },
  { value: 'crypto', label: '加密货币' },
  { value: 'cash', label: '现金' },
]

export const MARKETS = [
  { value: 'A', label: 'A股（沪深）' },
  { value: 'HK', label: '港股' },
  { value: 'US', label: '美股' },
  { value: 'ETF', label: '场内基金' },
  { value: 'FUND', label: '场外基金' },
  { value: 'CRYPTO', label: '加密货币' },
  { value: 'NONE', label: '不抓价（手填金额）' },
]

export const TXN_ACTIONS = [
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
  { value: 'dividend', label: '分红/利息' },
  { value: 'deposit', label: '入金' },
  { value: 'withdraw', label: '出金' },
  { value: 'other', label: '其它' },
]

const toMap = (arr) => Object.fromEntries(arr.map((x) => [x.value, x.label]))
export const CURRENCY_LABEL = toMap(CURRENCIES)
export const ASSET_TYPE_LABEL = toMap(ASSET_TYPES)
export const MARKET_LABEL = toMap(MARKETS)
export const TXN_ACTION_LABEL = toMap(TXN_ACTIONS)

export const HOLDING_SOURCES = [
  { value: 'manual', label: '手填' },
  { value: 'derived', label: '交易驱动' },
]
export const HOLDING_SOURCE_LABEL = toMap(HOLDING_SOURCES)

export const CURRENCY_SYMBOL = { CNY: '¥', USD: '$', HKD: 'HK$' }

// 隐私模式：开启后所有金额（经 fmt 输出的）显示为 ****
let _mask = (typeof localStorage !== 'undefined' && localStorage.getItem('privacy') === '1')
export const setMask = (v) => { _mask = !!v }
export const isMasked = () => _mask

// 数字千分位格式化（隐私模式下打码）
export const fmt = (n) =>
  (_mask ? '****' : (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
