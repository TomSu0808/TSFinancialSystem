// Pure helpers for the research workspace (kept JSX-free so node --test can run them).

export const TASK_ENTRIES = [
  {
    key: 'company',
    title: '研究一家公司',
    desc: '经营、估值、管理层与风险',
    template: 'investment-research',
    tools: '单公司研究 · 企业质量 · 管理层评估',
  },
  {
    key: 'earnings',
    title: '分析最新财报',
    desc: '业绩变化及投资逻辑影响',
    template: 'earnings-review',
    tools: '财报解读 · 财报委员会',
  },
  {
    key: 'holdings',
    title: '检查我的持仓',
    desc: '组合问题与持仓变化',
    template: 'portfolio-review',
    tools: '组合复盘 · 异动归因',
  },
  {
    key: 'thesis',
    title: '复查投资逻辑',
    desc: '原有假设是否仍然成立',
    template: 'thesis-tracker',
    tools: '投资论文追踪 · 买入前检查',
  },
]

export const RESEARCH_STATUS = {
  draft: { text: '草稿', color: 'default' },
  prompt_ready: { text: '准备好', color: 'processing' },
  queued: { text: '排队中', color: 'processing' },
  running: { text: '研究中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  cancelled: { text: '已取消', color: 'warning' },
}

export function safeJson(raw, fallback = null) {
  if (raw == null || raw === '') return fallback
  if (typeof raw === 'object') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function parseStructuredReport(report) {
  const data = safeJson(report?.report_json, null)
  if (!data || typeof data !== 'object') return null
  return data
}

export function parseMultiAgent(report) {
  return safeJson(report?.multi_agent_json, null)
}

export function parseSourceStatus(report) {
  return safeJson(report?.source_status_json, null)
}

export function parseUsage(report) {
  return safeJson(report?.usage_json, null)
}

export function parseBudget(report) {
  return safeJson(report?.budget_json, null)
}

export function parseSnapshot(report) {
  return safeJson(report?.input_snapshot_json, null)
}

export function sourceList(report, structured) {
  const provider = safeJson(report?.sources_json, []) || []
  const model = (structured?.sources || [])
  const seen = new Set()
  const out = []
  for (const source of [...provider, ...model]) {
    const key = source?.url || source?.title
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(source)
  }
  return out
}

export function evidenceLabel(kind, sourceMissing) {
  if (kind === 'fact') {
    return sourceMissing
      ? { text: '事实（来源缺失）', color: 'orange' }
      : { text: '有来源事实', color: 'green' }
  }
  if (kind === 'assumption') return { text: '待验证假设', color: 'orange' }
  return { text: '分析判断', color: 'blue' }
}

export function isActiveStatus(status) {
  return status === 'queued' || status === 'running'
}

export function versionLabel(report) {
  return `v${report?.version || 1}`
}

export function dataAsOf(report) {
  const snapshot = parseSnapshot(report)
  return report?.data_cutoff || snapshot?.data_cutoff || report?.completed_at || '未知'
}

export function compactQuestion(value, max = 32) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}…` : text
}

export function mergeSources(providerSources, newSources) {
  const seen = new Set((providerSources || []).map((s) => s?.url || s?.title))
  return [
    ...(providerSources || []),
    ...((newSources || []).filter((s) => {
      const key = s?.url || s?.title
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })),
  ]
}
