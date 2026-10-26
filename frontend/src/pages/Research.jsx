import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, Badge, Button, Card, Checkbox, Col, Collapse, Divider, Empty,
  Form, Input, message, Modal, Row, Segmented, Select, Space, Spin, Tabs,
  Tag, Timeline, Tooltip, Typography,
} from 'antd'
import {
  BookOutlined, BulbOutlined, CheckCircleOutlined, ClockCircleOutlined,
  CloseCircleOutlined, DeleteOutlined, ExclamationCircleOutlined, FileTextOutlined,
  LinkOutlined, ReloadOutlined, RobotOutlined, SendOutlined, StopOutlined,
  SyncOutlined, WarningOutlined, HistoryOutlined, DownOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  listResearchTemplates, listHoldings, listResearchReports,
  createResearchRun, previewResearchRun, refreshResearchRun,
  cancelResearchReport, deleteResearchReport, updateResearchRun,
  listResearchVersions, listResearchEvents, listTrackingCandidates,
  generateTrackingNotes, listResearchMessages, createResearchMessage,
  cancelResearchMessage, getResearchPreferences, saveResearchPreferences,
  getResearchReport, listAIKeys,
} from '../api'
import { useDisplaySettings } from '../displaySettings.jsx'
import {
  TASK_ENTRIES, RESEARCH_STATUS, parseStructuredReport, parseMultiAgent,
  parseSourceStatus, parseUsage, parseBudget, parseSnapshot, sourceList,
  evidenceLabel, isActiveStatus, dataAsOf, mergeSources,
} from '../research'

const { TextArea } = Input
const { Text, Title } = Typography

const MARKET_OPTIONS = [
  { value: 'US', label: 'US - 美股' },
  { value: 'HK', label: 'HK - 港股' },
  { value: 'A', label: 'A - A股' },
  { value: 'FUND', label: 'FUND - 基金' },
  { value: 'CRYPTO', label: 'CRYPTO - 加密' },
  { value: 'OTHER', label: 'OTHER - 其他' },
]

const LANG_OPTIONS = [
  { value: 'zh', label: '中文报告' },
  { value: 'en', label: 'English Report' },
]

const PROVIDER_OPTIONS = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'gpt', label: 'GPT' },
  { value: 'glm', label: 'GLM' },
  { value: 'claude', label: 'Claude' },
]

const MODEL_OPTIONS = {
  deepseek: [
    { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro' },
    { value: 'deepseek-v4-flash', label: 'deepseek-v4-flash' },
  ],
  gpt: [
    { value: 'gpt-5.5', label: 'gpt-5.5' },
    { value: 'gpt-5.4-mini', label: 'gpt-5.4-mini' },
  ],
  glm: [
    { value: 'glm-4.6', label: 'glm-4.6' },
    { value: 'glm-4-flash', label: 'glm-4-flash' },
  ],
  claude: [
    { value: 'claude-sonnet-4-5', label: 'claude-sonnet-4-5' },
    { value: 'claude-opus-4-1', label: 'claude-opus-4-1' },
  ],
}

const EXECUTION_LABELS = {
  standard: '标准研究',
  multi_agent: '多 Agent 协作',
}

const EVIDENCE_SOURCE_HINT = '有来源事实 = 模型给出可追溯来源；分析判断 = 基于事实的推理；待验证假设 = 尚未证实。'

const mdComponents = {
  h1: ({ children }) => (
    <h1 style={{ fontSize: 20, fontWeight: 700, marginTop: 20, marginBottom: 10, borderBottom: '1px solid #f0f0f0', paddingBottom: 6 }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: 17, fontWeight: 600, marginTop: 18, marginBottom: 8 }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: 15, fontWeight: 600, marginTop: 14, marginBottom: 6 }}>{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 style={{ fontSize: 14, fontWeight: 600, marginTop: 10, marginBottom: 4 }}>{children}</h4>
  ),
  p: ({ children }) => <p style={{ marginBottom: 10, lineHeight: 1.75 }}>{children}</p>,
  ul: ({ children }) => <ul style={{ paddingLeft: 22, marginBottom: 10, lineHeight: 1.7 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ paddingLeft: 22, marginBottom: 10, lineHeight: 1.7 }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: 3 }}>{children}</li>,
  blockquote: ({ children }) => (
    <blockquote style={{
      borderLeft: '3px solid #1677ff', margin: '10px 0', padding: '8px 14px',
      background: '#f0f5ff', borderRadius: '0 4px 4px 0', color: '#595959',
    }}>{children}</blockquote>
  ),
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', marginBottom: 14, borderRadius: 4 }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13, minWidth: 400 }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ border: '1px solid #d9d9d9', padding: '6px 12px', background: '#fafafa', fontWeight: 600, textAlign: 'left', whiteSpace: 'nowrap' }}>{children}</th>
  ),
  td: ({ children }) => <td style={{ border: '1px solid #d9d9d9', padding: '6px 12px', verticalAlign: 'top' }}>{children}</td>,
  pre: ({ children }) => (
    <pre style={{
      background: '#f5f5f5', padding: '10px 14px', borderRadius: 6,
      overflowX: 'auto', fontSize: 12, lineHeight: 1.65, marginBottom: 12,
      border: '1px solid #e8e8e8',
    }}>{children}</pre>
  ),
  code: ({ className, children }) => (
    className
      ? <code style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{children}</code>
      : <code style={{
        background: '#f0f0f0', padding: '1px 5px', borderRadius: 3, fontSize: '0.88em',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      }}>{children}</code>
  ),
  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" style={{ color: '#1677ff' }}>{children}</a>,
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid #f0f0f0', margin: '14px 0' }} />,
  strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
}

function newRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function statusConfig(status) {
  return RESEARCH_STATUS[status] || RESEARCH_STATUS.draft
}

function fmtTime(value) {
  if (!value) return ''
  const text = String(value)
  return text.includes('T') ? text.replace('T', ' ').slice(0, 16) : text.slice(0, 16)
}

export default function Research() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { displayCurrency } = useDisplaySettings()
  const [templates, setTemplates] = useState([])
  const [holdings, setHoldings] = useState([])
  const [reports, setReports] = useState([])
  const [activeCategory, setActiveCategory] = useState('全部')
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [activeTask, setActiveTask] = useState(null)
  const [viewReport, setViewReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [launching, setLaunching] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTick, setPreviewTick] = useState(0)
  const [preferences, setPreferences] = useState({})
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [aiKeys, setAIKeys] = useState([])
  const [toolsOpen, setToolsOpen] = useState(false)
  const [formSections, setFormSections] = useState([])

  const [runForm] = Form.useForm()
  const launchGuard = useRef(false)
  const formCardRef = useRef(null)
  const pollingRef = useRef(null)
  const reportsRef = useRef([])
  const initialQueryRef = useRef(true)

  const aiProvider = Form.useWatch('ai_provider', runForm)
  const useWebSearch = Form.useWatch('use_web_search', runForm)
  const executionMode = Form.useWatch('execution_mode', runForm) || 'standard'
  const includeHoldingContext = Form.useWatch('include_holding_context', runForm)
  const relatedHoldingId = Form.useWatch('related_holding_id', runForm)

  const isPortfolioReview = selectedTemplate?.key === 'portfolio-review'
  const isCommittee = selectedTemplate?.key === 'investment-team'
  const hasRunning = reports.some((r) => isActiveStatus(r.status))

  useEffect(() => { reportsRef.current = reports }, [reports])

  const refreshReports = useCallback(async () => {
    try {
      const fresh = await listResearchReports()
      setReports(fresh)
      setViewReport((current) => {
        if (!current) return current
        return fresh.find((r) => r.id === current.id) || current
      })
      return fresh
    } catch {
      return reportsRef.current
    }
  }, [])

  useEffect(() => {
    if (!hasRunning) {
      clearInterval(pollingRef.current)
      return undefined
    }
    const tick = () => refreshReports()
    tick()
    pollingRef.current = setInterval(tick, 2500)
    return () => clearInterval(pollingRef.current)
  }, [hasRunning, refreshReports])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      listResearchTemplates(),
      listHoldings(),
      listResearchReports(),
      getResearchPreferences().catch(() => ({})),
      listAIKeys().catch(() => []),
    ]).then(([ts, hs, rs, prefs, keys]) => {
      if (cancelled) return
      setTemplates(ts)
      setHoldings(hs)
      setReports(rs)
      setPreferences(prefs || {})
      setAIKeys(keys || [])
      runForm.setFieldsValue({
        investment_goal: prefs?.investment_goal || undefined,
        holding_period: prefs?.holding_period || undefined,
        risk_preference: prefs?.risk_preference || undefined,
      })

      const reportId = searchParams.get('report_id')
      if (reportId) {
        const target = rs.find((r) => String(r.id) === reportId)
        if (target) {
          setViewReport(target)
          setLoading(false)
          return
        }
      }

      const preset = searchParams.get('preset')
      const templateKey = searchParams.get('template')
      const taskKey = searchParams.get('task')
      const task = TASK_ENTRIES.find((t) => t.key === taskKey)
      const wanted = preset || templateKey || task?.template
      if (wanted) {
        const tpl = ts.find((t) => t.key === wanted)
        if (tpl) {
          setSelectedTemplate(tpl)
          if (task) setActiveTask(task.key)
          runForm.setFieldsValue({
            execution_mode: 'standard',
            report_language: 'zh',
            include_holding_context: true,
            use_web_search: true,
          })
        }
      }
      const hid = searchParams.get('holding_id')
      if (hid) {
        const h = hs.find((x) => String(x.id) === hid)
        if (h) {
          runForm.setFieldsValue({
            related_holding_id: h.id,
            target_name: h.name,
            symbol: h.symbol || undefined,
            market: h.market,
          })
          if (!wanted) {
            const tpl = ts.find((t) => t.key === 'investment-research')
            if (tpl) setSelectedTemplate(tpl)
          }
        }
      }
      setLoading(false)
    }).catch((e) => {
      if (!cancelled) {
        message.error('加载投研模板失败：' + (e.response?.data?.detail || e.message))
        setLoading(false)
      }
    })
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!searchParams.get('holding_id') || !initialQueryRef.current) return
    const hid = Number(searchParams.get('holding_id'))
    const h = holdings.find((x) => x.id === hid)
    if (h) {
      runForm.setFieldsValue({
        related_holding_id: h.id,
        target_name: h.name,
        symbol: h.symbol || undefined,
        market: h.market,
      })
      initialQueryRef.current = false
    }
  }, [holdings, searchParams, runForm])

  const categories = ['全部', ...Array.from(new Set(templates.map((t) => t.category)))]
  const filteredTemplates = activeCategory === '全部'
    ? templates
    : templates.filter((t) => t.category === activeCategory)

  const holdingOptions = useMemo(() => holdings.map((h) => ({
    value: h.id,
    label: `${h.name || h.symbol || '未命名'}${h.symbol ? ` (${h.symbol})` : ''} · ${h.market}${h.currency ? ` · ${h.currency}` : ''}`,
  })), [holdings])

  const selectTask = (task) => {
    const tpl = templates.find((t) => t.key === task.template)
    if (!tpl) return
    setActiveTask(task.key)
    setSelectedTemplate(tpl)
    setPreview(null)
    setPreviewOpen(false)
    setFormSections([])
    runForm.resetFields()
    runForm.setFieldsValue({
      execution_mode: 'standard',
      report_language: 'zh',
      include_holding_context: true,
      use_web_search: true,
      investment_goal: preferences.investment_goal || undefined,
      holding_period: preferences.holding_period || undefined,
      risk_preference: preferences.risk_preference || undefined,
    })
    setTimeout(() => formCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }

  const selectTemplate = (tpl) => {
    setActiveTask(null)
    setSelectedTemplate(tpl)
    setPreview(null)
    setPreviewOpen(false)
    setFormSections([])
    runForm.resetFields()
    runForm.setFieldsValue({
      execution_mode: 'standard',
      report_language: 'zh',
      include_holding_context: true,
      use_web_search: true,
      investment_goal: preferences.investment_goal || undefined,
      holding_period: preferences.holding_period || undefined,
      risk_preference: preferences.risk_preference || undefined,
    })
  }

  const handleProviderChange = () => {
    runForm.setFieldsValue({ ai_model: undefined })
  }

  const handleHoldingChange = useCallback((holdingId) => {
    if (!holdingId) return
    const h = holdings.find((x) => x.id === holdingId)
    if (h) {
      runForm.setFieldsValue({
        target_name: h.name,
        symbol: h.symbol || undefined,
        market: h.market,
      })
    }
  }, [holdings, runForm])

  const handleRetry = (report) => {
    const template = templates.find((t) => t.key === report.template_key)
    if (!template) return message.error('模板尚未加载，请稍后重试')
    setSelectedTemplate(template)
    setActiveTask(null)
    setViewReport(null)
    const snapshot = parseSnapshot(report) || {}
    runForm.setFieldsValue({
      ai_provider: report.provider,
      ai_model: report.model,
      report_language: report.report_language,
      target_name: report.target_name,
      symbol: report.symbol,
      market: report.market,
      related_holding_id: report.related_holding_id,
      execution_mode: report.execution_mode || 'standard',
      include_holding_context: snapshot.include_holding_context !== false,
      use_web_search: snapshot.web_search?.requested !== false,
    })
    message.info('已恢复模板和模型，请确认研究问题与输入预览后重新开始')
  }

  const buildPreviewPayload = () => {
    const values = runForm.getFieldsValue()
    return {
      template_key: selectedTemplate?.key,
      target_name: values.target_name || null,
      symbol: values.symbol || null,
      market: values.market || null,
      related_holding_id: values.related_holding_id ? Number(values.related_holding_id) : null,
      report_language: values.report_language || 'zh',
      display_currency: displayCurrency,
      execution_mode: isCommittee ? (values.execution_mode || 'standard') : 'standard',
      include_holding_context: values.include_holding_context !== false,
      use_web_search: values.use_web_search !== false,
      ai_provider: values.ai_provider || null,
      ai_model: values.ai_model || null,
    }
  }

  const fetchPreview = useCallback(async () => {
    if (!selectedTemplate) return
    const values = runForm.getFieldsValue()
    if (!isPortfolioReview && !String(values.target_name || '').trim()) {
      setPreview(null)
      setPreviewError('请先填写或选择研究对象，再预览本次输入。')
      return
    }
    setPreviewLoading(true)
    setPreviewError('')
    try {
      const result = await previewResearchRun(buildPreviewPayload())
      setPreview(result)
    } catch (e) {
      setPreview(null)
      setPreviewError(e.response?.data?.detail || e.message || '预览失败')
    } finally {
      setPreviewLoading(false)
    }
  }, [selectedTemplate, isPortfolioReview, isCommittee, displayCurrency, runForm]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!previewOpen || !selectedTemplate) return undefined
    const timer = setTimeout(fetchPreview, 350)
    return () => clearTimeout(timer)
  }, [previewOpen, previewTick, selectedTemplate, fetchPreview])

  const localPreferenceText = (values) => {
    const parts = []
    if (values.investment_goal) parts.push(`投资目标：${values.investment_goal}`)
    if (values.holding_period) parts.push(`持有周期：${values.holding_period}`)
    if (values.risk_preference) parts.push(`风险偏好：${values.risk_preference}`)
    return parts.join('；')
  }

  const handleSavePreferences = async () => {
    const values = runForm.getFieldsValue()
    setSavingPreferences(true)
    try {
      const saved = await saveResearchPreferences({
        investment_goal: values.investment_goal || null,
        holding_period: values.holding_period || null,
        risk_preference: values.risk_preference || null,
      })
      setPreferences(saved)
      message.success('研究偏好已保存')
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setSavingPreferences(false)
    }
  }

  const ambiguousIdentity = (values) => {
    if (values.related_holding_id || !values.target_name) return false
    const matches = holdings.filter((h) => h.name === values.target_name)
    const identities = new Set(matches.map((h) => `${h.market || ''}:${h.symbol || ''}:${h.currency || ''}`))
    return identities.size > 1 || matches.length > 1
  }

  const handleLaunch = async () => {
    if (launchGuard.current || !selectedTemplate) return
    let values
    try {
      values = await runForm.validateFields()
    } catch {
      return
    }
    if (isPortfolioReview && values.include_holding_context === false) {
      message.error('组合复盘必须携带持仓数据')
      return
    }
    if (ambiguousIdentity(values)) {
      message.error('该公司名称对应多个持仓/市场，请先选择一个具体持仓，系统不会猜测研究标的。')
      return
    }
    if (values.include_holding_context !== false && isPortfolioReview) {
      // okay
    }
    if (preview?.multi_agent?.supported === false && (values.execution_mode === 'multi_agent')) {
      message.error(preview.multi_agent.reason || '该标的不支持多 Agent 研究')
      return
    }

    const savedPrefs = localPreferenceText(preferences)
    const currentPrefs = localPreferenceText(values)
    const extraParts = [values.extra_instruction]
    if (currentPrefs && currentPrefs !== savedPrefs) {
      extraParts.push(`【本次研究偏好】${currentPrefs}`)
    }
    const payload = {
      ...buildPreviewPayload(),
      extra_instruction: extraParts.filter(Boolean).join('\n') || null,
      ai_provider: values.ai_provider || null,
      ai_model: values.ai_model || null,
      idempotency_key: newRequestId(),
    }
    launchGuard.current = true
    setLaunching(true)
    try {
      const report = await createResearchRun(payload)
      message.success(report.status === 'completed'
        ? '研究已完成'
        : '研究任务已启动；进度来自后台真实事件')
      setReports((prev) => [report, ...prev.filter((r) => r.id !== report.id)])
      setViewReport(report)
      await refreshReports()
      setPreviewOpen(false)
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || ''
      if (detail.includes('AI 设置') || detail.includes('API Key')) {
        message.error({
          content: detail + ' 请点击右上角头像 → 个人资料 → AI 设置进行配置。',
          duration: 8,
        })
      } else {
        message.error('启动失败：' + detail)
      }
    } finally {
      launchGuard.current = false
      setLaunching(false)
    }
  }

  const handleRefresh = async (report) => {
    try {
      const updated = await refreshResearchRun(report.id)
      setReports((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      if (viewReport?.id === updated.id) setViewReport(updated)
    } catch (e) {
      message.error('刷新失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const handleCancel = async (report) => {
    try {
      const result = await cancelResearchReport(report.id)
      await refreshReports()
      if (result.provider_cancelled === false) {
        message.warning(result.message || '已标记取消，但 Provider 未确认中断')
      } else {
        message.success('已取消')
      }
    } catch (e) {
      message.error('取消失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const handleDelete = (id) => {
    Modal.confirm({
      title: '确认删除该报告？',
      content: '报告关联的追问消息和事件记录也会删除；其他版本保留但不再指向它。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteResearchReport(id)
          setReports((prev) => prev.filter((r) => r.id !== id))
          if (viewReport?.id === id) setViewReport(null)
          message.success('已删除')
        } catch (e) {
          message.error('删除失败：' + (e.response?.data?.detail || e.message))
        }
      },
    })
  }

  const handleUpdate = async (report, values) => {
    const updated = await updateResearchRun(report.id, {
      ...values,
      idempotency_key: newRequestId(),
    })
    setReports((prev) => [updated, ...prev.filter((r) => r.id !== updated.id)])
    setViewReport(updated)
    message.success(`已创建 v${updated.version || (report.version || 1) + 1} 更新任务`)
    return updated
  }

  const handleOpenReport = async (reportOrId) => {
    if (typeof reportOrId === 'number') {
      const found = reports.find((r) => r.id === reportOrId)
      if (found) {
        setViewReport(found)
        return
      }
      try {
        const fetched = await getResearchReport(reportOrId)
        setReports((prev) => [fetched, ...prev.filter((r) => r.id !== fetched.id)])
        setViewReport(fetched)
      } catch (e) {
        message.error('加载版本失败：' + (e.response?.data?.detail || e.message))
      }
      return
    }
    setViewReport(reportOrId)
  }

  const currentProvider = aiProvider || aiKeys.find((k) => k.is_default)?.provider

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        <RobotOutlined style={{ marginRight: 8 }} />
        AI 投研工作台
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
        先选任务，再确认研究对象、本次问题和研究方式；提交前可展开查看实际携带的数据。
      </Text>
      <Text type="secondary" style={{ display: 'block', fontSize: 11, marginBottom: 16 }}>
        研究只做记录、分析与复盘，不会下单、撤单、转账或修改持仓/现金/交易。
        Research framework adapted from{' '}
        <a href="https://github.com/xbtlin/ai-berkshire" target="_blank" rel="noreferrer">xbtlin/ai-berkshire</a>
        {' '}· MIT License
      </Text>

      <Spin spinning={loading}>
        <Card
          size="small"
          title={<Space><BulbOutlined /><span>今天想研究什么？</span></Space>}
          style={{ marginBottom: 12 }}
          styles={{ body: { padding: 12 } }}
        >
          <Row gutter={[10, 10]}>
            {TASK_ENTRIES.map((task) => {
              const selected = activeTask === task.key
              return (
                <Col xs={12} lg={6} key={task.key}>
                  <Card
                    size="small"
                    hoverable
                    onClick={() => selectTask(task)}
                    style={{
                      height: '100%', cursor: 'pointer',
                      border: selected ? '2px solid #1677ff' : '1px solid #e8e8e8',
                    }}
                    styles={{ body: { padding: '12px 12px' } }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>{task.title}</div>
                    <div style={{ color: '#666', fontSize: 12, lineHeight: 1.5 }}>{task.desc}</div>
                    <div style={{ color: '#999', fontSize: 11, marginTop: 6 }}>{task.tools}</div>
                  </Card>
                </Col>
              )
            })}
          </Row>

          <Collapse
            ghost
            size="small"
            activeKey={toolsOpen ? ['tools'] : []}
            onChange={(keys) => setToolsOpen(keys.includes('tools'))}
            style={{ marginTop: 8 }}
            items={[{
              key: 'tools',
              label: <Text style={{ fontSize: 12 }}><FileTextOutlined /> 全部研究工具（{templates.length}）</Text>,
              children: (
                <div>
                  <Tabs
                    size="small"
                    activeKey={activeCategory}
                    onChange={setActiveCategory}
                    items={categories.map((c) => ({ key: c, label: c }))}
                    style={{ marginBottom: 6 }}
                  />
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {filteredTemplates.map((tpl) => (
                      <Card
                        key={tpl.key}
                        size="small"
                        hoverable
                        onClick={() => selectTemplate(tpl)}
                        style={{
                          width: 190, cursor: 'pointer',
                          border: selectedTemplate?.key === tpl.key ? '2px solid #1677ff' : '1px solid #d9d9d9',
                        }}
                        styles={{ body: { padding: '8px 10px' } }}
                      >
                        <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                          {tpl.priority && <Tag color="red" style={{ marginRight: 4, fontSize: 10 }}>推荐</Tag>}
                          {tpl.name}
                        </div>
                        <Tag style={{ fontSize: 10 }}>{tpl.category}</Tag>
                        <div style={{ fontSize: 11, color: '#888', lineHeight: 1.35, marginTop: 4 }}>
                          {tpl.description}
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              ),
            }]}
          />
        </Card>

        <Row gutter={16}>
          {(!viewReport || selectedTemplate) && (
          <Col xs={24} lg={viewReport ? 8 : 14}>
            {selectedTemplate ? (
              <Card
                ref={formCardRef}
                size="small"
                title={(
                  <div>
                    <Space wrap>
                      <FileTextOutlined />
                      <span>{selectedTemplate.name}</span>
                      <Tag color="geekblue" style={{ fontSize: 10 }}>{EXECUTION_LABELS[executionMode] || '标准研究'}</Tag>
                    </Space>
                    {selectedTemplate.description && (
                      <div style={{ fontSize: 11, fontWeight: 400, color: '#888', marginTop: 2 }}>
                        {selectedTemplate.description}
                      </div>
                    )}
                  </div>
                )}
                style={{ marginBottom: 12 }}
                extra={(
                  <Button size="small" type="text" onClick={() => { setSelectedTemplate(null); setActiveTask(null) }}>
                    收起
                  </Button>
                )}
              >
                <Form
                  form={runForm}
                  layout="vertical"
                  size="small"
                  initialValues={{
                    report_language: 'zh',
                    execution_mode: 'standard',
                    use_web_search: true,
                    include_holding_context: true,
                  }}
                  onValuesChange={() => setPreviewTick((n) => n + 1)}
                >
                  {isPortfolioReview ? (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12, fontSize: 12 }}
                      message="将自动读取当前全部持仓与现金，数字由后端统一折算；无需手动填写公司名称。"
                    />
                  ) : (
                    <>
                      <Form.Item
                        name="related_holding_id"
                        label="研究对象（已有持仓可选）"
                        style={{ marginBottom: 8 }}
                        rules={selectedTemplate?.key === 'thesis-tracker'
                          ? [{ required: true, message: '投资论文追踪需要选择一个已有持仓' }]
                          : []}
                        extra={isCommittee ? '多 Agent 需要明确代码和市场；选择持仓可自动带入。' : undefined}
                      >
                        <Select
                          allowClear
                          placeholder="选择持仓，自动填入名称、代码、市场"
                          options={holdingOptions}
                          showSearch
                          filterOption={(input, opt) => (opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
                          onChange={handleHoldingChange}
                        />
                      </Form.Item>
                      <Form.Item
                        name="target_name"
                        label={isCommittee ? '公司/证券名称' : '公司名称'}
                        rules={[{ required: true, message: '请填写公司或证券名称' }]}
                        style={{ marginBottom: 8 }}
                      >
                        <Input placeholder="例：腾讯控股" />
                      </Form.Item>
                      <Row gutter={8}>
                        <Col xs={24} sm={12}>
                          <Form.Item name="symbol" label="代码" style={{ marginBottom: 8 }}>
                            <Input placeholder="例：700.HK" />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12}>
                          <Form.Item name="market" label="市场" style={{ marginBottom: 8 }}>
                            <Select placeholder="选择市场" allowClear options={MARKET_OPTIONS} />
                          </Form.Item>
                        </Col>
                      </Row>
                      {relatedHoldingId && (
                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                          已选择持仓；若名称/代码/市场与持仓不一致，提交会被拒绝，系统不会猜测。
                        </Text>
                      )}
                    </>
                  )}

                  {isCommittee && (
                    <div style={{ marginBottom: 12 }}>
                      <Text strong style={{ display: 'block', marginBottom: 6 }}>研究方式</Text>
                      <Segmented
                        block
                        options={[
                          { value: 'standard', label: '标准讨论' },
                          { value: 'multi_agent', label: '多 Agent 协作' },
                        ]}
                        value={executionMode}
                        onChange={(v) => {
                          runForm.setFieldsValue({ execution_mode: v })
                          setPreviewTick((n) => n + 1)
                        }}
                      />
                      <Alert
                        type={executionMode === 'multi_agent' ? 'warning' : 'info'}
                        showIcon
                        style={{ marginTop: 8, fontSize: 12 }}
                        message={executionMode === 'multi_agent'
                          ? '实际调用固定版本的 TradingAgents：基本面、行情、机构新闻三个分析师；默认关闭 social；多空与风险各一轮。进程隔离，取消会终止 Worker。'
                          : '沿用现有投委会讨论逻辑，由当前 Provider 一次生成报告。'}
                      />
                    </div>
                  )}

                  <Form.Item
                    name="extra_instruction"
                    label="本次问题（最重要）"
                    style={{ marginBottom: 8 }}
                  >
                    <TextArea
                      rows={3}
                      placeholder={isPortfolioReview
                        ? '例：当前组合最需要处理的问题是什么？'
                        : '例：如果资本开支继续增长，原结论会怎样变化？'}
                    />
                  </Form.Item>

                  <Collapse
                    size="small"
                    ghost
                    activeKey={formSections}
                    onChange={(keys) => {
                      setFormSections(keys)
                      if (keys.includes('preview')) {
                        setPreviewOpen(true)
                        setPreviewTick((n) => n + 1)
                      }
                    }}
                    items={[
                      {
                        key: 'advanced',
                        label: <Text style={{ fontSize: 12 }}>高级设置</Text>,
                        children: (
                          <div>
                            <Row gutter={8}>
                              <Col xs={24} sm={12}>
                                <Form.Item name="ai_provider" label="模型提供商" style={{ marginBottom: 8 }}>
                                  <Select
                                    allowClear
                                    placeholder="使用账户默认服务"
                                    options={PROVIDER_OPTIONS}
                                    onChange={handleProviderChange}
                                  />
                                </Form.Item>
                              </Col>
                              <Col xs={24} sm={12}>
                                <Form.Item name="ai_model" label="模型" style={{ marginBottom: 8 }}>
                                  <Select
                                    allowClear
                                    placeholder="使用该服务默认模型"
                                    options={MODEL_OPTIONS[currentProvider] || []}
                                  />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item name="report_language" label="报告语言" style={{ marginBottom: 8 }}>
                              <Select options={LANG_OPTIONS} />
                            </Form.Item>
                            <Form.Item
                              name="include_holding_context"
                              label="携带个人持仓信息"
                              valuePropName="checked"
                              style={{ marginBottom: 4 }}
                            >
                              <Checkbox disabled={isPortfolioReview}>
                                {isPortfolioReview ? '组合复盘必须携带' : '携带持仓、成本、现金、历史研究与笔记'}
                              </Checkbox>
                            </Form.Item>
                            <Form.Item
                              name="use_web_search"
                              label="请求联网检索"
                              valuePropName="checked"
                              style={{ marginBottom: 2 }}
                            >
                              <Checkbox>向 Provider 请求联网</Checkbox>
                            </Form.Item>
                            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                              {currentProvider && currentProvider !== 'gpt'
                                ? `当前 ${currentProvider} 未接入本系统联网检索；开启也只表示请求，不等于搜索成功。`
                                : '联网开启不等于搜索成功；成功返回也不等于内容已核验。'}
                            </Text>
                          </div>
                        ),
                      },
                      {
                        key: 'prefs',
                        label: <Text style={{ fontSize: 12 }}>研究偏好（可选，可由你编辑）</Text>,
                        children: (
                          <div>
                            <Row gutter={8}>
                              <Col xs={24} sm={12}>
                                <Form.Item name="investment_goal" label="投资目标" style={{ marginBottom: 8 }}>
                                  <Input placeholder="如长期增值 / 退休储备" />
                                </Form.Item>
                              </Col>
                              <Col xs={24} sm={12}>
                                <Form.Item name="holding_period" label="持有周期" style={{ marginBottom: 8 }}>
                                  <Input placeholder="如 3–5 年" />
                                </Form.Item>
                              </Col>
                              <Col xs={24} sm={12}>
                                <Form.Item name="risk_preference" label="风险偏好" style={{ marginBottom: 8 }}>
                                  <Input placeholder="如稳健 / 激进" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Button size="small" loading={savingPreferences} onClick={handleSavePreferences}>
                              保存为默认偏好
                            </Button>
                            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
                              偏好只来自你的填写，不从资产规模推断。
                            </Text>
                          </div>
                        ),
                      },
                      {
                        key: 'preview',
                        label: <Text style={{ fontSize: 12 }}><DownOutlined /> 查看本次研究输入</Text>,
                        children: (
                          <div>
                            <Space size={4} wrap style={{ marginBottom: 8 }}>
                              <Tag color={preview?.execution_mode === 'multi_agent' ? 'purple' : 'blue'}>
                                {preview?.execution_label || (executionMode === 'multi_agent' ? '多 Agent 协作' : '标准研究')}
                              </Tag>
                              {preview?.data_cutoff && <Tag>数据时点 {preview.data_cutoff}</Tag>}
                              <Button size="small" icon={<ReloadOutlined />} loading={previewLoading} onClick={fetchPreview}>
                                刷新预览
                              </Button>
                            </Space>
                            {previewError && <Alert type="error" showIcon message={previewError} style={{ marginBottom: 8 }} />}
                            {preview?.multi_agent?.supported === false && (
                              <Alert type="error" showIcon style={{ marginBottom: 8 }}
                                message="当前标的不支持多 Agent 协作" description={preview.multi_agent.reason} />
                            )}
                            {preview && (
                              <Input.TextArea
                                readOnly
                                value={[
                                  `研究对象：${preview.target?.name || '—'}`,
                                  `市场/代码：${preview.target?.market || '未知'} / ${preview.target?.symbol || '缺失'}`,
                                  `研究方式：${preview.execution_label}`,
                                  `数据时点：${preview.data_cutoff}`,
                                  `携带：持仓=${preview.includes?.holdings ? '是' : '否'}，成本=${preview.includes?.cost ? '是' : '否'}，现金=${preview.includes?.cash ? '是' : '否'}，历史研究=${preview.includes?.prior_reports || 0} 条，笔记=${preview.includes?.notes || 0} 条`,
                                  preview.multi_agent?.ticker ? `TradingAgents 代码：${preview.multi_agent.ticker}` : '',
                                  ...(preview.warnings || []).map((w) => `提示：${w}`),
                                  preview.multi_agent?.reason ? `提示：${preview.multi_agent.reason}` : '',
                                  ...(preview.multi_agent?.limitations || []).map((w) => `限制：${w}`),
                                  ...((preview.multi_agent?.excluded_holdings || []).length
                                    ? [`排除的其他币种/资产：${preview.multi_agent.excluded_holdings.map((h) => `${h.name || h.symbol}(${h.currency})`).join('、')}`]
                                    : []),
                                  preview.context_preview_md ? `\n--- 数据预览 ---\n${preview.context_preview_md.slice(0, 5000)}` : '',
                                ].filter(Boolean).join('\n')}
                                autoSize={{ minRows: 8, maxRows: 16 }}
                                style={{ fontSize: 11 }}
                              />
                            )}
                          </div>
                        ),
                      },
                    ]}
                  />
                </Form>

                <Space style={{ marginTop: 8 }} wrap>
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={launching}
                    onClick={handleLaunch}
                  >
                    {launching ? '提交中…' : '开始研究'}
                  </Button>
                  <Button onClick={() => {
                    setFormSections((prev) => Array.from(new Set([...prev, 'preview'])))
                    setPreviewOpen(true)
                    setPreviewTick((n) => n + 1)
                  }}>
                    查看本次输入
                  </Button>
                </Space>
              </Card>
            ) : (
              <Card size="small" style={{ marginBottom: 12 }}>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="选择上方任务或展开「全部研究工具」开始"
                />
              </Card>
            )}
          </Col>
          )}

          <Col xs={24} lg={viewReport ? (selectedTemplate ? 16 : 24) : 10}>
            {viewReport ? (
              <ReportDetail
                report={viewReport}
                onBack={() => setViewReport(null)}
                onRefresh={handleRefresh}
                onCancel={handleCancel}
                onDelete={handleDelete}
                onRetry={() => handleRetry(viewReport)}
                onOpenReport={handleOpenReport}
                onUpdate={handleUpdate}
                onChanged={refreshReports}
              />
            ) : (
              <ReportList
                reports={reports}
                onSelect={handleOpenReport}
                onRefresh={handleRefresh}
                onDelete={handleDelete}
              />
            )}
          </Col>
        </Row>
      </Spin>
    </div>
  )
}

function ReportList({ reports, onSelect, onRefresh, onDelete }) {
  return (
    <Card
      size="small"
      title={<Space><BookOutlined /><span>已保存报告</span></Space>}
      styles={{ body: { padding: '8px 12px' } }}
    >
      {reports.length === 0 ? (
        <Empty description="暂无报告，选择一个任务开始研究" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {reports.map((r) => {
            const st = statusConfig(r.status)
            const active = isActiveStatus(r.status)
            return (
              <Card
                key={r.id}
                size="small"
                hoverable
                onClick={() => onSelect(r)}
                styles={{ body: { padding: '8px 10px' } }}
                style={{ cursor: 'pointer' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title || r.target_name}
                    </div>
                    <Space style={{ marginTop: 4 }} size={4} wrap>
                      <Badge status={st.color === 'success' ? 'success' : st.color === 'error' ? 'error' : st.color === 'processing' ? 'processing' : 'default'} />
                      <Tag color={st.color} style={{ fontSize: 11 }}>{st.text}</Tag>
                      {r.execution_mode === 'multi_agent' && <Tag color="purple" style={{ fontSize: 10 }}>多 Agent</Tag>}
                      {(r.version || 1) > 1 && <Tag color="gold" style={{ fontSize: 10 }}>v{r.version}</Tag>}
                      {r.report_language && <Tag style={{ fontSize: 10 }}>{r.report_language === 'en' ? 'EN' : '中文'}</Tag>}
                      {r.provider && <Tag style={{ fontSize: 10 }}>{r.provider}</Tag>}
                      <Text type="secondary" style={{ fontSize: 11 }}>{fmtTime(r.updated_at)}</Text>
                    </Space>
                  </div>
                  <Space size={4} style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                    {active && r.execution_mode !== 'multi_agent' && (
                      <Tooltip title="刷新状态">
                        <Button size="small" icon={<ReloadOutlined />} onClick={() => onRefresh(r)} />
                      </Tooltip>
                    )}
                    <Tooltip title="删除">
                      <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(r.id)} />
                    </Tooltip>
                  </Space>
                </div>
                {r.error_message && (
                  <Text type="danger" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    {r.error_message.slice(0, 140)}
                  </Text>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </Card>
  )
}

function EvidenceList({ title, items, empty = '暂无' }) {
  if (!items || items.length === 0) return null
  return (
    <div style={{ marginTop: 10 }}>
      <Text strong style={{ fontSize: 12 }}>{title}</Text>
      <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map((item, index) => {
          const label = evidenceLabel(item.kind, item.source_missing)
          const text = typeof item === 'string' ? item : item.text
          const source = typeof item === 'string' ? null : item.source
          return (
            <div key={index} style={{ fontSize: 12, lineHeight: 1.6 }}>
              <Tag color={label.color} style={{ fontSize: 10 }}>{label.text}</Tag>
              <span>{text}</span>
              {source && <Text type="secondary" style={{ fontSize: 11 }}>（来源：{source}）</Text>}
              {item?.period && <Tag style={{ fontSize: 10, marginLeft: 4 }}>{item.period}</Tag>}
              {item?.as_of && <Text type="secondary" style={{ fontSize: 11 }}> {item.as_of}</Text>}
              {item?.source_missing && <Text type="warning" style={{ fontSize: 11 }}> 来源缺失</Text>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StructuredSummary({ report }) {
  const structured = parseStructuredReport(report)
  const snapshot = parseSnapshot(report)
  if (!structured) {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 10 }}
        message="该报告没有结构化摘要（可能是旧版本）"
        description={`以下降级展示完整 Markdown 原文。数据时点：${dataAsOf(report)}。`}
      />
    )
  }
  if (structured.degraded) {
    return (
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 10 }}
        message="结构化摘要解析失败，已降级展示完整正文"
        description={structured.degradation_reason || '模型未按要求返回可解析的结构化数据；系统没有编造缺失字段。'}
      />
    )
  }
  return (
    <div style={{ marginBottom: 12 }}>
      {structured.summary && (
        <Card size="small" style={{ marginBottom: 8, background: '#f6ffed', borderColor: '#b7eb8f' }}>
          <Text strong style={{ fontSize: 13 }}>核心结论</Text>
          <div style={{ marginTop: 4, fontSize: 14, lineHeight: 1.7 }}>{structured.summary}</div>
        </Card>
      )}
      <Row gutter={[10, 10]}>
        <Col xs={24} md={12}>
          <Card size="small" style={{ height: '100%' }}>
            <Text strong style={{ fontSize: 12 }}>关键事实与来源</Text>
            {structured.key_facts?.length
              ? <EvidenceList items={structured.key_facts} />
              : <div style={{ color: '#999', fontSize: 12, marginTop: 6 }}>未返回结构化事实</div>}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" style={{ height: '100%' }}>
            <Text strong style={{ fontSize: 12 }}>主要风险与反证</Text>
            {structured.risks?.length
              ? <EvidenceList items={structured.risks} />
              : <div style={{ color: '#999', fontSize: 12, marginTop: 6 }}>未返回结构化风险</div>}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" style={{ height: '100%' }}>
            <Text strong style={{ fontSize: 12 }}>对持仓/研究目标的影响</Text>
            <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.7 }}>
              {structured.impact || <Text type="secondary">未提供</Text>}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" style={{ height: '100%' }}>
            <Text strong style={{ fontSize: 12 }}>下一步观察事项</Text>
            {structured.next_watch?.length
              ? <EvidenceList items={structured.next_watch} />
              : <div style={{ color: '#999', fontSize: 12, marginTop: 6 }}>未提供</div>}
          </Card>
        </Col>
      </Row>
      {structured.changes && (
        <Card size="small" style={{ marginTop: 10, borderColor: '#ffe58f' }}>
          <Space wrap>
            <Tag color="gold">更新对照</Tag>
            {structured.changes.comparison_method === 'deterministic' && <Tag>自动文本对照</Tag>}
          </Space>
          <Row gutter={[10, 8]} style={{ marginTop: 8 }}>
            {[
              ['新增事实', 'added_facts'],
              ['得到支持的假设', 'assumptions_supported'],
              ['被推翻的假设', 'assumptions_invalidated'],
              ['结论变化及依据', 'conclusion_changes'],
              ['仍未解决的跟踪事项', 'unresolved_tracking'],
              ['资料覆盖不足', 'coverage_gaps'],
            ].map(([label, key]) => (
              <Col xs={24} md={12} key={key}>
                <Text strong style={{ fontSize: 11 }}>{label}</Text>
                {(structured.changes[key] || []).length ? (
                  <ul style={{ margin: '4px 0 0 18px', padding: 0, fontSize: 12, lineHeight: 1.6 }}>
                    {structured.changes[key].map((item, index) => <li key={index}>{item}</li>)}
                  </ul>
                ) : (
                  <div style={{ color: '#999', fontSize: 11 }}>无 / 未提供</div>
                )}
              </Col>
            ))}
          </Row>
        </Card>
      )}
      <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 11 }}>
        {EVIDENCE_SOURCE_HINT} 数据时点：{dataAsOf(report)}
        {snapshot?.display_currency ? `；展示币种：${snapshot.display_currency}` : ''}
      </Text>
    </div>
  )
}

function SourcePanel({ report }) {
  const structured = parseStructuredReport(report)
  const status = parseSourceStatus(report) || structured?.source_status || {}
  const sources = sourceList(report, structured)
  return (
    <div style={{ marginBottom: 10 }}>
      <Space size={4} wrap>
        <Tag color={status.status === 'sources_returned' ? 'green' : status.status === 'not_requested' ? 'default' : 'orange'}>
          {status.status || 'unknown'}
        </Tag>
        {status.requested && <Tag>已请求检索</Tag>}
        {status.provider_supports_search === false && <Tag color="orange">Provider 不支持检索</Tag>}
        <Tag color="default">未标记为“已核验”</Tag>
        <Text type="secondary" style={{ fontSize: 11 }}>来源 {sources.length} 条</Text>
      </Space>
      <div style={{ marginTop: 4, fontSize: 11, color: '#888' }}>{status.message || '来源状态未知。'}</div>
      {sources.length > 0 && (
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {sources.map((source, index) => (
            <a
              key={index}
              href={source.url || undefined}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
            >
              <LinkOutlined /> {source.title || source.url}
              {source.retrieved_at ? ` · 获取于 ${fmtTime(source.retrieved_at)}` : ''}
            </a>
          ))}
        </div>
      )}
      {status.status && status.status !== 'sources_returned' && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 6, fontSize: 11 }}
          message={
            status.status === 'agent_data_tools'
              ? '多 Agent 数据工具已获取资料，但本轮未逐条核验引用可访问性；请以公司公告、财报和监管披露为准。'
              : status.status === 'not_requested'
                ? '本次未请求联网检索，回答仅基于平台上下文与模型知识。'
                : status.status === 'unsupported_provider'
                  ? '该 Provider 未接入本系统联网检索；报告中的来源为模型引用，未由系统抓取或核验。'
                  : '没有可验证的新来源时，报告不会把模型知识包装成最新事实。'
          }
        />
      )}
    </div>
  )
}

function MultiAgentPanel({ report }) {
  const multi = parseMultiAgent(report)
  if (!multi) return null
  const roles = multi.roles || {}
  const sections = [
    ['分析师观点', 'analysts', ['fundamentals', 'market', 'news'], { fundamentals: '基本面', market: '行情', news: '机构新闻' }],
    ['多空讨论', 'research_debate', ['bull', 'bear'], { bull: '多方', bear: '空方' }],
    ['风险讨论', 'risk_debate', ['aggressive', 'conservative', 'neutral'], { aggressive: '激进', conservative: '保守', neutral: '中性' }],
  ]
  const items = []
  sections.forEach(([title, key, names, labels]) => {
    const values = roles[key] || {}
    const children = names.map((name) => values[name] ? (
      <div key={name} style={{ marginBottom: 10 }}>
        <Text strong style={{ fontSize: 12 }}>{labels[name]}</Text>
        <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.65, marginTop: 4, color: '#444' }}>
          {String(values[name]).slice(0, 6000)}
        </div>
      </div>
    ) : null).filter(Boolean)
    if (children.length) items.push({ key, label: title, children: <div>{children}</div> })
  })
  if (roles.manager) items.push({ key: 'manager', label: '研究经理', children: <div style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{String(roles.manager).slice(0, 6000)}</div> })
  if (roles.strategy) items.push({ key: 'strategy', label: '策略观点与情景（非交易指令）', children: <div style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{String(roles.strategy).slice(0, 6000)}</div> })
  return (
    <Card size="small" style={{ marginBottom: 10 }}>
      <Space size={4} wrap>
        <Tag color="purple">TradingAgents {multi.engine_version || ''}</Tag>
        <Tag>{multi.engine_commit ? `commit ${String(multi.engine_commit).slice(0, 8)}` : '固定版本'}</Tag>
        {multi.rating && <Tag color="geekblue">{multi.rating}</Tag>}
        <Tag color="default">无执行工具</Tag>
      </Space>
      <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
        多 Agent 观点仅用于研究；策略节点不包含下单、撤单或转账能力。
        {multi.tool_usage?.calls ? ` 本次数据工具调用 ${multi.tool_usage.calls} 次。` : ''}
      </div>
      {items.length > 0 && (
        <Collapse size="small" style={{ marginTop: 8 }} items={items} />
      )}
      {multi.memory_note && (
        <Alert type="info" showIcon style={{ marginTop: 8, fontSize: 11 }} message={multi.memory_note} />
      )}
    </Card>
  )
}

function RunEvents({ report, events }) {
  if (!events || events.length === 0) {
    return isActiveStatus(report.status)
      ? <Alert type="info" showIcon icon={<Spin size="small" />} message="等待后台真实事件…" style={{ marginBottom: 10 }} />
      : null
  }
  const shown = events.slice(-14)
  return (
    <Card size="small" title={<Space><ClockCircleOutlined /><span>执行进度（后台事件）</span></Space>} style={{ marginBottom: 10 }}
      styles={{ body: { padding: '10px 12px' } }}>
      <Timeline
        items={shown.map((event) => ({
          color: event.status === 'failed' ? 'red' : event.status === 'cancelled' ? 'gray'
            : event.status === 'completed' ? 'green' : event.status === 'started' ? 'blue' : 'gray',
          children: (
            <div style={{ fontSize: 11 }}>
              <Space size={4} wrap>
                <Tag style={{ fontSize: 10 }}>{event.stage}</Tag>
                <Text type="secondary">{fmtTime(event.created_at)}</Text>
              </Space>
              <div style={{ marginTop: 2 }}>{event.message}</div>
            </div>
          ),
        }))}
      />
    </Card>
  )
}

function ReportDetail({
  report, onBack, onRefresh, onCancel, onDelete, onRetry,
  onOpenReport, onUpdate, onChanged,
}) {
  const navigate = useNavigate()
  const st = statusConfig(report.status)
  const active = isActiveStatus(report.status)
  const [events, setEvents] = useState([])
  const [versions, setVersions] = useState([])
  const [trackingOpen, setTrackingOpen] = useState(false)
  const [trackingLoading, setTrackingLoading] = useState(false)
  const [trackingSaving, setTrackingSaving] = useState(false)
  const [trackingData, setTrackingData] = useState(null)
  const [trackingItems, setTrackingItems] = useState([])
  const [updateOpen, setUpdateOpen] = useState(false)
  const [updateSaving, setUpdateSaving] = useState(false)
  const [updateForm] = Form.useForm()

  const loadEvents = useCallback(() => {
    listResearchEvents(report.id).then(setEvents).catch(() => {})
  }, [report.id])

  useEffect(() => {
    loadEvents()
    listResearchVersions(report.id).then(setVersions).catch(() => [])
  }, [report.id, loadEvents])

  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(loadEvents, 3000)
    return () => clearInterval(timer)
  }, [active, loadEvents])

  const structured = parseStructuredReport(report)
  const budget = parseBudget(report)
  const usage = parseUsage(report)
  const snapshot = parseSnapshot(report)

  const openTracking = async () => {
    setTrackingOpen(true)
    setTrackingLoading(true)
    try {
      const data = await listTrackingCandidates(report.id)
      setTrackingData(data)
      setTrackingItems((data.items || []).map((item) => ({
        ...item,
        selected: true,
        review_date: item.review_date || '',
        trigger_condition: item.trigger_condition || '',
        metric: item.metric || '',
      })))
    } catch (e) {
      message.error('提取跟踪事项失败：' + (e.response?.data?.detail || e.message))
      setTrackingOpen(false)
    } finally {
      setTrackingLoading(false)
    }
  }

  const saveTracking = async () => {
    const items = trackingItems.filter((item) => item.selected && item.text?.trim()).map((item) => ({
      text: item.text,
      metric: item.metric || null,
      review_date: item.review_date || null,
      trigger_condition: item.trigger_condition || null,
      symbol: item.symbol || null,
      status: 'active',
    }))
    if (!items.length) {
      message.warning('请至少选择一条跟踪事项')
      return
    }
    setTrackingSaving(true)
    try {
      const result = await generateTrackingNotes(report.id, { items })
      if (result.reused) message.info('该报告已有跟踪事项，未重复创建')
      else message.success(`已保存 ${result.notes.length} 条跟踪事项`)
      setTrackingOpen(false)
      onChanged?.()
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setTrackingSaving(false)
    }
  }

  const submitUpdate = async () => {
    const values = await updateForm.validateFields()
    setUpdateSaving(true)
    try {
      await onUpdate(report, values)
      setUpdateOpen(false)
      updateForm.resetFields()
    } catch (e) {
      message.error('创建更新失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setUpdateSaving(false)
    }
  }

  return (
    <Card
      size="small"
      title={(
        <Space wrap>
          <Button size="small" onClick={onBack}>← 返回</Button>
          <span style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 300 }}>
            {report.title || report.target_name}
          </span>
          <Tag color={st.color}>{st.text}</Tag>
          {(report.version || 1) > 1 && <Tag color="gold">v{report.version}</Tag>}
        </Space>
      )}
      extra={(
        <Space size={4} wrap>
          {active && report.execution_mode !== 'multi_agent' && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => onRefresh(report)}>刷新</Button>
          )}
          {active && (
            <Button size="small" danger icon={<StopOutlined />} onClick={() => onCancel(report)}>取消</Button>
          )}
          {report.status === 'completed' && (
            <Button size="small" type="primary" ghost icon={<SyncOutlined />} onClick={() => setUpdateOpen(true)}>
              更新这份研究
            </Button>
          )}
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(report.id)} />
        </Space>
      )}
      styles={{ body: { padding: '10px 12px' } }}
    >
      <Space size={6} style={{ marginBottom: 10, flexWrap: 'wrap' }}>
        <Tag color={st.color}>{st.text}</Tag>
        <Tag>{report.report_language === 'en' ? 'English Report' : '中文报告'}</Tag>
        {report.execution_mode === 'multi_agent' ? <Tag color="purple">多 Agent</Tag> : <Tag color="blue">标准研究</Tag>}
        {report.provider && <Tag color="cyan">{report.provider}</Tag>}
        {report.model && <Tag color="geekblue">{report.model}</Tag>}
        {report.template_key && <Tag color="purple">{report.template_key}</Tag>}
        <Text type="secondary" style={{ fontSize: 11 }}>数据时点 {dataAsOf(report)}</Text>
      </Space>

      {(report.version || 1) > 1 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 10, fontSize: 12 }}
          message={`这是第 ${report.version} 版研究${report.parent_report_id ? `，基于报告 #${report.parent_report_id}` : ''}`}
          action={report.parent_report_id ? (
            <Button size="small" onClick={() => onOpenReport(report.parent_report_id)}>查看上一版</Button>
          ) : null}
        />
      )}
      {versions.length > 1 && (
        <div style={{ marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>版本链：</Text>
          <Space size={4} wrap>
            {versions.map((v) => (
              <Button
                key={v.id}
                size="small"
                type={v.id === report.id ? 'primary' : 'default'}
                ghost={v.id === report.id}
                onClick={() => onOpenReport(v.id)}
              >
                v{v.version} · {v.status}
              </Button>
            ))}
          </Space>
        </div>
      )}

      <RunEvents report={report} events={events} />

      {active && (
        <Alert
          type="info"
          showIcon
          icon={<Spin size="small" />}
          message="任务正在后台执行"
          style={{ marginBottom: 10 }}
        />
      )}

      {report.status === 'failed' && report.error_message && (
        <Alert
          type="error"
          showIcon
          icon={<ExclamationCircleOutlined />}
          message={report.error_message}
          action={<Button size="small" onClick={onRetry}>重新开始</Button>}
          style={{ marginBottom: 10 }}
        />
      )}

      {report.status === 'cancelled' && report.error_message && (
        <Alert
          type="warning"
          showIcon
          message="已取消"
          description={report.error_message}
          style={{ marginBottom: 10 }}
        />
      )}

      {report.report_md && <StructuredSummary report={report} />}
      {report.report_md && <SourcePanel report={report} />}
      {report.report_md && report.execution_mode === 'multi_agent' && <MultiAgentPanel report={report} />}

      {report.report_md ? (
        <div style={{
          marginBottom: 10, maxHeight: 760, overflowY: 'auto',
          padding: '18px 20px', border: '1px solid #f0f0f0', borderRadius: 12,
          background: '#fff', color: '#262626', fontSize: 14, lineHeight: 1.85,
        }}>
          <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>完整报告正文</Text>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {report.report_md}
          </ReactMarkdown>
        </div>
      ) : (
        !active && report.status !== 'failed' && (
          <Empty description="暂无报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginBottom: 10 }} />
        )
      )}

      {report.status === 'completed' && report.report_md && (
        <Space wrap style={{ marginBottom: 10 }}>
          <Button icon={<CheckCircleOutlined />} size="small" onClick={openTracking}>
            预览并保存跟踪事项
          </Button>
          <Button icon={<HistoryOutlined />} size="small" onClick={() => setUpdateOpen(true)}>
            更新这份研究
          </Button>
          <Text type="secondary" style={{ fontSize: 11 }}>
            跟踪事项写入决策日志，不会触发交易。
          </Text>
        </Space>
      )}

      {budget && (
        <Collapse
          size="small"
          ghost
          items={[{
            key: 'cost',
            label: <Text style={{ fontSize: 11 }}>用量、预算与费用</Text>,
            children: (
              <div style={{ fontSize: 11, lineHeight: 1.7 }}>
                <div>模型调用：{usage?.usage?.calls ?? '未知'} 次；输入 {usage?.usage?.input_tokens ?? '未知'}，输出 {usage?.usage?.output_tokens ?? '未知'}，缓存读取 {usage?.usage?.cached_input_tokens ?? 0}。</div>
                <div>费用：{usage?.cost?.amount != null ? `${usage.cost.amount} ${usage.cost.currency}` : (usage?.cost?.reason || '未知')}</div>
                {usage?.cost?.basis && <div>计价依据：{usage.cost.basis}</div>}
                <div>预算状态：{budget.status || '未知'} {budget.stop_reasons?.length ? `；${budget.stop_reasons.join('；')}` : ''}</div>
                <div>限制：调用 {budget.limits?.max_calls} 次，输出 {budget.limits?.max_output_tokens} tokens，时间 {budget.limits?.max_seconds}s。</div>
              </div>
            ),
          }]}
        />
      )}

      {report.status === 'completed' && report.report_md && (
        <ReportChat report={report} />
      )}

      <Collapse
        size="small"
        ghost
        style={{ marginTop: 8 }}
        items={[{
          key: 'debug',
          label: <Text style={{ fontSize: 11 }}>输入快照与调试信息</Text>,
          children: (
            <div style={{ fontSize: 11 }}>
              {snapshot && (
                <div style={{ marginBottom: 8 }}>
                  <Text strong>输入快照</Text>
                  <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 220, overflowY: 'auto', fontSize: 11 }}>
                    {JSON.stringify(snapshot, null, 2)}
                  </pre>
                </div>
              )}
              {report.input_context_md && (
                <div style={{ marginBottom: 8 }}>
                  <Text strong>平台上下文</Text>
                  <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 220, overflowY: 'auto', fontSize: 11 }}>
                    {report.input_context_md}
                  </pre>
                </div>
              )}
              {report.prompt_md && (
                <div>
                  <Text strong>最终 Prompt</Text>
                  <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 220, overflowY: 'auto', fontSize: 11 }}>
                    {report.prompt_md}
                  </pre>
                </div>
              )}
            </div>
          ),
        }]}
      />

      <Modal
        title="预览并保存跟踪事项"
        open={trackingOpen}
        onCancel={() => setTrackingOpen(false)}
        onOk={saveTracking}
        okText="保存所选"
        confirmLoading={trackingSaving}
        width={720}
        destroyOnHidden
      >
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 8 }}>
          这些事项会写入投资笔记/决策日志；没有明确日期的条目不会生成复查日期。
        </Text>
        {trackingData?.existing?.length > 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 8 }}
            message={`该报告已有 ${trackingData.existing.length} 条跟踪事项，保存不会重复创建`}
            action={<a onClick={() => { setTrackingOpen(false); navigate(`/notes?source_report_id=${report.id}`) }}>查看笔记</a>}
          />
        )}
        {trackingLoading ? <Spin /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 420, overflowY: 'auto' }}>
            {(trackingItems || []).map((item, index) => (
              <Card key={index} size="small" styles={{ body: { padding: 10 } }}>
                <Checkbox
                  checked={item.selected}
                  onChange={(e) => setTrackingItems((prev) => prev.map((x, i) => i === index ? { ...x, selected: e.target.checked } : x))}
                >
                  <span style={{ fontSize: 12 }}>{item.text}</span>
                </Checkbox>
                <Row gutter={8} style={{ marginTop: 6 }}>
                  <Col xs={24} sm={8}>
                    <Input
                      size="small"
                      value={item.metric}
                      placeholder="观察指标（可选）"
                      onChange={(e) => setTrackingItems((prev) => prev.map((x, i) => i === index ? { ...x, metric: e.target.value } : x))}
                    />
                  </Col>
                  <Col xs={24} sm={8}>
                    <Input
                      size="small"
                      value={item.review_date}
                      placeholder="复查日期 YYYY-MM-DD（可选）"
                      onChange={(e) => setTrackingItems((prev) => prev.map((x, i) => i === index ? { ...x, review_date: e.target.value } : x))}
                    />
                  </Col>
                  <Col xs={24} sm={8}>
                    <Input
                      size="small"
                      value={item.trigger_condition}
                      placeholder="事件条件（如下一次财报后）"
                      onChange={(e) => setTrackingItems((prev) => prev.map((x, i) => i === index ? { ...x, trigger_condition: e.target.value } : x))}
                    />
                  </Col>
                </Row>
              </Card>
            ))}
            {(!trackingItems || trackingItems.length === 0) && <Empty description="未找到跟踪事项" />}
          </div>
        )}
      </Modal>

      <Modal
        title="更新这份研究"
        open={updateOpen}
        onCancel={() => setUpdateOpen(false)}
        onOk={submitUpdate}
        okText="生成新版本"
        confirmLoading={updateSaving}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 10, fontSize: 12 }}
          message="新版本会保留旧报告和版本关系，并要求模型明确列出新增事实、假设变化、结论变化、未解决事项和资料缺口。没有新资料时会直接说明。"
        />
        <Form form={updateForm} layout="vertical" size="small" initialValues={{ use_web_search: true }}>
          <Form.Item name="extra_instruction" label="本次更新重点（可选）">
            <TextArea rows={3} placeholder="例：重点核查最新财报后的资本开支指引" />
          </Form.Item>
          <Form.Item name="use_web_search" label="请求联网核查新资料" valuePropName="checked">
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

function ReportChat({ report }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [useSearch, setUseSearch] = useState(false)
  const sendingRef = useRef(false)
  const listRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listResearchMessages(report.id)
      setMessages(data || [])
    } catch {
      // The report remains readable if chat history cannot load.
    } finally {
      setLoading(false)
    }
  }, [report.id])

  useEffect(() => {
    load()
  }, [load])

  const hasActive = messages.some((m) => m.role === 'assistant' && isActiveStatus(m.status))

  useEffect(() => {
    if (!hasActive) return undefined
    const timer = setInterval(load, 2500)
    return () => clearInterval(timer)
  }, [hasActive, load])

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages.length, hasActive])

  const send = async (questionOverride) => {
    const question = (questionOverride ?? input).trim()
    if (!question || sendingRef.current || hasActive) return
    sendingRef.current = true
    setSending(true)
    try {
      await createResearchMessage(report.id, {
        question,
        use_web_search: useSearch,
        request_id: newRequestId(),
      })
      setInput('')
      await load()
    } catch (e) {
      // Keep the typed text so the user can retry without retyping.
      message.error('追问失败：' + (e.response?.data?.detail || e.message))
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }

  const stop = async (messageId) => {
    try {
      const result = await cancelResearchMessage(report.id, messageId)
      if (result.provider_cancelled === false) {
        message.warning(result.message || '已取消，但 Provider 未确认中断')
      }
      await load()
    } catch (e) {
      message.error('停止失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const lastUserQuestion = () => {
    const userMessages = messages.filter((m) => m.role === 'user')
    return userMessages.length ? userMessages[userMessages.length - 1].content : ''
  }

  useEffect(() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
    if (lastAssistant?.status === 'failed' && !input) {
      setInput(lastUserQuestion())
    }
  }, [messages, input])

  return (
    <Card
      size="small"
      title={<Space><SendOutlined /><span>围绕本报告提问</span></Space>}
      style={{ marginTop: 10 }}
      styles={{ body: { padding: 10 } }}
    >
      <div
        ref={listRef}
        className="research-chat-list"
        style={{ maxHeight: 420, overflowY: 'auto', marginBottom: 8 }}
      >
        {loading && messages.length === 0 && <Spin size="small" />}
        {!loading && messages.length === 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            首次提问会自动携带原报告和输入快照，无需复制报告内容。
          </Text>
        )}
        {messages.map((m) => {
          const isUser = m.role === 'user'
          const active = m.role === 'assistant' && isActiveStatus(m.status)
          return (
            <div
              key={m.id}
              style={{
                display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start',
                marginBottom: 8,
              }}
            >
              <div style={{
                maxWidth: '88%', minWidth: 120,
                background: isUser ? '#e6f4ff' : '#fafafa',
                border: '1px solid ' + (isUser ? '#bae0ff' : '#eee'),
                borderRadius: 10, padding: '8px 10px',
              }}>
                <Space size={4} wrap style={{ marginBottom: 4 }}>
                  <Tag color={isUser ? 'blue' : m.status === 'failed' ? 'red' : m.status === 'cancelled' ? 'default' : 'green'} style={{ fontSize: 10 }}>
                    {isUser ? '你' : m.status === 'failed' ? '失败' : m.status === 'cancelled' ? '已取消' : active ? '生成中' : '助手'}
                  </Tag>
                  {m.used_web_search && <Tag color={m.search_status === 'sources_returned' ? 'green' : 'orange'} style={{ fontSize: 10 }}>{m.search_status || '已请求检索'}</Tag>}
                  {m.context_compressed && <Tag style={{ fontSize: 10 }}>历史已压缩</Tag>}
                </Space>
                {m.content ? (
                  <div style={{ fontSize: 12, lineHeight: 1.7 }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{m.content}</ReactMarkdown>
                  </div>
                ) : active ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>正在生成…</Text>
                ) : null}
                {m.error_message && (
                  <Alert type="error" showIcon style={{ marginTop: 6, fontSize: 11 }} message={m.error_message} />
                )}
                {m.data_as_of && (
                  <div style={{ fontSize: 10, color: '#999', marginTop: 4 }}>数据时点：{m.data_as_of}</div>
                )}
                {(() => {
                  const newSources = (() => { try { return JSON.parse(m.new_sources_json || '[]') } catch { return [] } })()
                  return newSources.length > 0 && (
                    <div style={{ marginTop: 4, fontSize: 10 }}>
                      <Text strong style={{ fontSize: 10 }}>新增来源：</Text>
                      {newSources.map((s, i) => (
                        <a key={i} href={s.url} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>
                          {s.title || s.url}
                        </a>
                      ))}
                    </div>
                  )
                })()}
                {active && (
                  <Button size="small" danger icon={<StopOutlined />} style={{ marginTop: 6 }} onClick={() => stop(m.id)}>
                    停止
                  </Button>
                )}
                {m.status === 'failed' && !m.provider_response_id && (
                  <Button size="small" style={{ marginTop: 6 }} onClick={() => send(lastUserQuestion())}>
                    重试上一问题
                  </Button>
                )}
                {m.status === 'failed' && m.provider_response_id && (
                  <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
                    该请求已提交给 Provider，可能已产生费用；未自动重试。请确认后手动发送。
                  </Text>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <TextArea
        rows={2}
        value={input}
        disabled={hasActive}
        onChange={(e) => setInput(e.target.value)}
        placeholder="例：如果资本开支继续增长，原结论会怎样变化？"
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault()
            send()
          }
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, gap: 8, flexWrap: 'wrap' }}>
        <Checkbox checked={useSearch} onChange={(e) => setUseSearch(e.target.checked)} style={{ fontSize: 11 }}>
          补充联网核查（会注明新增来源及时间）
        </Checkbox>
        <Button
          type="primary"
          size="small"
          icon={<SendOutlined />}
          loading={sending}
          disabled={!input.trim() || hasActive}
          onClick={() => send()}
        >
          发送
        </Button>
      </div>
      <Text type="secondary" style={{ display: 'block', fontSize: 10, marginTop: 4 }}>
        追问及回答独立保存，不覆盖原报告；失败时保留输入以便重试。
      </Text>
    </Card>
  )
}
