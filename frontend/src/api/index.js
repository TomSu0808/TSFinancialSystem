import axios from 'axios'

// 同源 /api，由 Vite 代理到后端；上云后前后端同域也无需改
const client = axios.create({ baseURL: '/api', timeout: 60000 })

// ---- 登录态（token 存 localStorage）----
const TOKEN_KEY = 'token'
const USER_KEY = 'user'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const getStoredUser = () => {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}
const saveAuth = ({ access_token, user }) => {
  localStorage.setItem(TOKEN_KEY, access_token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  return user
}
export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 每个请求自动带上 Bearer token
client.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

// 401（未登录/过期）→ 清登录态并通知 App 跳登录页
client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      clearAuth()
      window.dispatchEvent(new Event('auth:logout'))
    }
    return Promise.reject(err)
  },
)

// ---- 认证 ----
export const register = (data) =>
  client.post('/auth/register', data).then((r) => saveAuth(r.data))
export const login = (data) =>
  client.post('/auth/login', data).then((r) => saveAuth(r.data))
export const logout = () => clearAuth()
export const changePassword = (data) =>
  client.post('/auth/change-password', data).then((r) => r.data)

// ---- 平台 ----
export const listPlatforms = () => client.get('/platforms').then((r) => r.data)
export const createPlatform = (data) => client.post('/platforms', data).then((r) => r.data)
export const updatePlatform = (id, data) => client.put(`/platforms/${id}`, data).then((r) => r.data)
export const deletePlatform = (id) => client.delete(`/platforms/${id}`).then((r) => r.data)

// ---- 资产 ----
export const listHoldings = (params) => client.get('/holdings', { params }).then((r) => r.data)
export const createHolding = (data) => client.post('/holdings', data).then((r) => r.data)
export const updateHolding = (id, data) => client.put(`/holdings/${id}`, data).then((r) => r.data)
export const deleteHolding = (id) => client.delete(`/holdings/${id}`).then((r) => r.data)
export const refreshPrices = () => client.post('/holdings/refresh-prices').then((r) => r.data)

// ---- 汇率 ----
export const getRate = () => client.get('/fx/rate').then((r) => r.data)
export const refreshRate = () => client.post('/fx/refresh').then((r) => r.data)

// ---- 汇总 ----
export const getSummary = (currency) =>
  client.get('/summary', { params: { currency } }).then((r) => r.data)

// ---- 投资心得 ----
export const listNotes = () => client.get('/notes').then((r) => r.data)
export const createNote = (data) => client.post('/notes', data).then((r) => r.data)
export const updateNote = (id, data) => client.put(`/notes/${id}`, data).then((r) => r.data)
export const deleteNote = (id) => client.delete(`/notes/${id}`).then((r) => r.data)

// ---- 净值走势 ----
export const getSnapshots = (days = 90) =>
  client.get('/snapshots', { params: { days } }).then((r) => r.data)

// ---- 交易记录 ----
export const listTransactions = (params) =>
  client.get('/transactions', { params }).then((r) => r.data)
export const createTransaction = (data) => client.post('/transactions', data).then((r) => r.data)
export const updateTransaction = (id, data) => client.put(`/transactions/${id}`, data).then((r) => r.data)
export const deleteTransaction = (id) => client.delete(`/transactions/${id}`).then((r) => r.data)

// ---- 备份 ----
export const exportBackup = () => client.get('/backup').then((r) => r.data)
export const importBackup = (payload) => client.post('/backup/import', payload).then((r) => r.data)

export default client
