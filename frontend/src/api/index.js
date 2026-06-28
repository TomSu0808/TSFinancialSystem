import axios from 'axios'

// 同源 /api，由 Vite 代理到后端；上云后前后端同域也无需改
const client = axios.create({ baseURL: '/api', timeout: 300000 })

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
  client.post('/auth/register', data).then((r) => {
    const user = saveAuth(r.data)
    if (r.data.dev_verification_url) user.dev_verification_url = r.data.dev_verification_url
    return user
  })
export const login = (data) =>
  client.post('/auth/login', data).then((r) => saveAuth(r.data))
export const logout = () => clearAuth()
export const changePassword = (data) =>
  client.post('/auth/change-password', data).then((r) => r.data)
export const getMe = () =>
  client.get('/auth/me').then((r) => r.data)
export const resendVerification = () =>
  client.post('/auth/resend-verification').then((r) => r.data)
export const verifyEmail = (token) =>
  client.post('/auth/verify-email', { token }).then((r) => r.data)
export const changeEmail = (data) =>
  client.post('/auth/change-email', data).then((r) => r.data)
export const forgotPassword = (email) =>
  client.post('/auth/forgot-password', { email }).then((r) => r.data)
export const resetPassword = (token, new_password) =>
  client.post('/auth/reset-password', { token, new_password }).then((r) => r.data)
export const listSecurityQuestions = () =>
  client.get('/auth/security-questions').then((r) => r.data)
export const getRecoveryQuestion = (username) =>
  client.post('/auth/recovery-question', { username }).then((r) => r.data)
export const resetPasswordBySecurityQuestion = (data) =>
  client.post('/auth/reset-password-by-security-question', data).then((r) => r.data)
export const setSecurityQuestion = (data) =>
  client.post('/auth/set-security-question', data).then((r) => r.data)

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

// ---- 投资心得 / 决策日志 ----
export const listNotes = (params) => client.get('/notes', { params }).then((r) => r.data)
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
// ---- 旧版 CSV 导入（保留兼容）----
export const previewTransactionImport = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return client.post('/transactions/import/preview', fd).then((r) => r.data)
}
export const commitTransactionImport = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return client.post('/transactions/import/commit', fd).then((r) => r.data)
}

// ---- 新版导入系统（Phase 1）----
export const previewImport = (file, { platform_id, broker_type, mapping }) => {
  const fd = new FormData()
  fd.append('file', file)
  if (platform_id != null) fd.append('platform_id', platform_id)
  fd.append('broker_type', broker_type || 'futu')
  if (mapping) fd.append('mapping', JSON.stringify(mapping))
  return client.post('/imports/preview', fd).then((r) => r.data)
}
export const commitImport = (importSessionId, { selected_rows, edited_rows }) => {
  const fd = new FormData()
  if (selected_rows) fd.append('selected_rows', selected_rows)
  if (edited_rows) fd.append('edited_rows', JSON.stringify(edited_rows))
  return client.post(`/imports/${importSessionId}/commit`, fd).then((r) => r.data)
}
export const getImportReconciliation = (importSessionId) =>
  client.get(`/imports/${importSessionId}/reconciliation`).then((r) => r.data)
export const listImports = () =>
  client.get('/imports').then((r) => r.data)
export const getImportDetail = (importSessionId) =>
  client.get(`/imports/${importSessionId}`).then((r) => r.data)
export const getDataStatus = () =>
  client.get('/summary/data-status').then((r) => r.data)

// ---- 备份 ----
export const exportBackup = () => client.get('/backup').then((r) => r.data)
export const importBackup = (payload) => client.post('/backup/import', payload).then((r) => r.data)

// ---- 投研工作台 ----
export const listResearchTemplates = () => client.get('/research/templates').then((r) => r.data)
export const generateResearchPrompt = (data) => client.post('/research/prompts', data).then((r) => r.data)
export const listResearchReports = (params) => client.get('/research/reports', { params }).then((r) => r.data)
export const createResearchReport = (data) => client.post('/research/reports', data).then((r) => r.data)
export const getResearchReport = (id) => client.get(`/research/reports/${id}`).then((r) => r.data)
export const updateResearchReport = (id, data) => client.put(`/research/reports/${id}`, data).then((r) => r.data)
export const deleteResearchReport = (id) => client.delete(`/research/reports/${id}`).then((r) => r.data)
// AI 投研任务（直接调用 AI，无需手动复制 prompt）
export const createResearchRun = (data) => client.post('/research/runs', data).then((r) => r.data)
export const refreshResearchRun = (id) => client.post(`/research/runs/${id}/refresh`).then((r) => r.data)
export const cancelResearchReport = (id) => client.post(`/research/reports/${id}/cancel`).then((r) => r.data)
export const generateTrackingNotes = (reportId) =>
  client.post(`/research/reports/${reportId}/tracking-notes`).then((r) => r.data)

// ---- 持仓研究摘要 ----
export const getHoldingResearchBrief = (holdingId) =>
  client.get(`/holdings/${holdingId}/research-brief`).then((r) => r.data)

// ---- AI Key 管理（BYOK）----
export const listAIKeys = () => client.get('/settings/ai-keys').then((r) => r.data)
export const saveAIKey = (data) => client.post('/settings/ai-keys', data).then((r) => r.data)
export const updateAIKey = (id, data) => client.put(`/settings/ai-keys/${id}`, data).then((r) => r.data)
export const deleteAIKey = (id) => client.delete(`/settings/ai-keys/${id}`).then((r) => r.data)
export const testAIKey = (data) => client.post('/settings/ai-keys/test', data).then((r) => r.data)

// ---- 自动化任务 ----
export const getAutomationStatus = () => client.get('/automation/status').then((r) => r.data)
export const runNow = () => client.post('/automation/run-now').then((r) => r.data)
export const listAutomationRuns = () => client.get('/automation/runs').then((r) => r.data)

// ---- 提醒规则 ----
export const listAlertRules = () => client.get('/alerts/rules').then((r) => r.data)
export const createAlertRule = (data) => client.post('/alerts/rules', data).then((r) => r.data)
export const updateAlertRule = (id, data) => client.put(`/alerts/rules/${id}`, data).then((r) => r.data)
export const deleteAlertRule = (id) => client.delete(`/alerts/rules/${id}`).then((r) => r.data)

// ---- 提醒事件 ----
export const listAlertEvents = (params) => client.get('/alerts/events', { params }).then((r) => r.data)
export const getUnreadCount = () => client.get('/alerts/events/unread-count').then((r) => r.data)
export const markEventRead = (id) => client.post(`/alerts/events/${id}/read`).then((r) => r.data)
export const markAllRead = () => client.post('/alerts/events/read-all').then((r) => r.data)
export const dismissEvent = (id) => client.post(`/alerts/events/${id}/dismiss`).then((r) => r.data)
export const evaluateAlerts = () => client.post('/alerts/evaluate').then((r) => r.data)

export default client
