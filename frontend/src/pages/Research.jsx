import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Badge, Button, Card, Col, Collapse, Empty,
  Form, Input, message, Modal, Row, Select, Space, Spin, Steps,
  Switch, Tabs, Tag, Tooltip, Typography,
} from 'antd'
import {
  BookOutlined, BulbOutlined, CheckCircleOutlined, ClockCircleOutlined,
  CloseCircleOutlined, DeleteOutlined, ExclamationCircleOutlined,
  FileTextOutlined, LinkOutlined, ReloadOutlined, RobotOutlined, SendOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate } from 'react-router-dom'
import {
  listResearchTemplates, listHoldings,
  listResearchReports, createResearchRun,
  refreshResearchRun, cancelResearchReport, deleteResearchReport,
  generateTrackingNotes,
} from '../api'

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

const SKILL_MODE = {
  'investment-research': '深度模式',
  'investment-team':     '深度模式',
  'portfolio-review':    '深度模式',
  'earnings-review':     '深度模式',
  'industry-research':   '深度模式',
  'industry-funnel':     '深度模式',
  'investment-checklist':'快速模式',
  'news-pulse':          '快速模式',
  'thesis-tracker':      '快速模式',
  'quality-screen':      '快速模式',
}

const MODE_COLOR = { '深度模式': 'magenta', '快速模式': 'green', '普通模式': 'default' }

const CATEGORY_COLOR = {
  '深度研究': 'blue',
  '财报分析': 'cyan',
  '行业筛选': 'orange',
  '持仓管理': 'purple',
}

const STATUS_CONFIG = {
  draft:        { text: '草稿',     color: 'default',    icon: null },
  prompt_ready: { text: '准备好',   color: 'processing', icon: null },
  queued:       { text: '排队中',   color: 'processing', icon: <ClockCircleOutlined /> },
  running:      { text: 'AI研究中', color: 'processing', icon: <Spin size="small" /> },
  completed:    { text: '已完成',   color: 'success',    icon: null },
  failed:       { text: '失败',     color: 'error',      icon: <CloseCircleOutlined /> },
  cancelled:    { text: '已取消',   color: 'warning',    icon: null },
}

const DISCLAIMER_ZH = 'AI 生成内容仅供研究记录，不构成投资建议。请自行核验关键数据和结论。'
const DISCLAIMER_EN = 'AI-generated content is for research logging only and does not constitute investment advice. Please independently verify key data and conclusions.'

// Styled component overrides for ReactMarkdown
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
  p: ({ children }) => (
    <p style={{ marginBottom: 10, lineHeight: 1.75 }}>{children}</p>
  ),
  ul: ({ children }) => (
    <ul style={{ paddingLeft: 22, marginBottom: 10, lineHeight: 1.7 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ paddingLeft: 22, marginBottom: 10, lineHeight: 1.7 }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ marginBottom: 3 }}>{children}</li>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{
      borderLeft: '3px solid #1677ff', margin: '10px 0', padding: '8px 14px',
      background: '#f0f5ff', borderRadius: '0 4px 4px 0', color: '#595959',
    }}>
      {children}
    </blockquote>
  ),
  // Wrap table in a scrollable div so it doesn't break mobile layout
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', marginBottom: 14, borderRadius: 4 }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13, minWidth: 400 }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  th: ({ children }) => (
    <th style={{ border: '1px solid #d9d9d9', padding: '6px 12px', background: '#fafafa', fontWeight: 600, textAlign: 'left', whiteSpace: 'nowrap' }}>
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td style={{ border: '1px solid #d9d9d9', padding: '6px 12px', verticalAlign: 'top' }}>
      {children}
    </td>
  ),
  // pre wraps fenced code blocks
  pre: ({ children }) => (
    <pre style={{
      background: '#f5f5f5', padding: '10px 14px', borderRadius: 6,
      overflowX: 'auto', fontSize: 12, lineHeight: 1.65, marginBottom: 12,
      border: '1px solid #e8e8e8',
    }}>
      {children}
    </pre>
  ),
  // code: inline when no className, block when className=language-*
  code: ({ className, children }) => {
    const isBlock = Boolean(className)
    if (isBlock) {
      return <code style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{children}</code>
    }
    return (
      <code style={{
        background: '#f0f0f0', padding: '1px 5px', borderRadius: 3,
        fontSize: '0.88em', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      }}>
        {children}
      </code>
    )
  },
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: '#1677ff' }}>{children}</a>
  ),
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid #f0f0f0', margin: '14px 0' }} />,
  strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
}

const RUN_STEPS = ['准备上下文', '提交 AI 任务', '联网搜索与分析', '生成报告', '保存结果']

function getStepCurrent(status) {
  switch (status) {
    case 'queued':    return 1
    case 'running':   return 2
    case 'completed': return 4
    case 'failed':    return 2
    case 'cancelled': return 1
    default:          return 0
  }
}

function getStepStatus(status) {
  if (status === 'completed') return 'finish'
  if (status === 'failed')    return 'error'
  return 'process'
}

export default function Research() {
  const navigate = useNavigate()
  const [templates, setTemplates] = useState([])
  const [holdings, setHoldings] = useState([])
  const [reports, setReports] = useState([])
  const [activeCategory, setActiveCategory] = useState('全部')
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [viewReport, setViewReport] = useState(null)
  const [generatingTracking, setGeneratingTracking] = useState(false)

  const [runForm] = Form.useForm()
  const [launching, setLaunching] = useState(false)
  const useWebSearch = Form.useWatch('use_web_search', runForm)
  const aiProvider = Form.useWatch('ai_provider', runForm) || 'deepseek'

  const pollingRef = useRef(null)
  const reportsRef = useRef([])

  const hasRunning = reports.some((r) => r.status === 'running' || r.status === 'queued')

  useEffect(() => {
    reportsRef.current = reports
  }, [reports])

  const refreshReports = useCallback(async ({ refreshRunning = false } = {}) => {
    try {
      if (refreshRunning) {
        const running = reportsRef.current.filter((r) => r.status === 'running' || r.status === 'queued')
        await Promise.all(running.map((r) => refreshResearchRun(r.id).catch(() => null)))
      }
      const fresh = await listResearchReports()
      setReports(fresh)
      setViewReport((current) => {
        if (!current) return current
        return fresh.find((r) => r.id === current.id) || current
      })
      return fresh
    } catch {
      // ignore
      return reportsRef.current
    }
  }, [])

  useEffect(() => {
    if (!hasRunning) {
      clearInterval(pollingRef.current)
      return undefined
    }
    const tick = () => refreshReports({ refreshRunning: true })
    tick()
    pollingRef.current = setInterval(tick, 3000)
    return () => clearInterval(pollingRef.current)
  }, [hasRunning, refreshReports])

  useEffect(() => {
    listResearchTemplates().then(setTemplates).catch(() => {})
    listHoldings().then(setHoldings).catch(() => {})
    listResearchReports().then(setReports).catch(() => {})
  }, [])

  const categories = ['全部', ...Array.from(new Set(templates.map((t) => t.category)))]
  const filteredTemplates = activeCategory === '全部'
    ? templates
    : templates.filter((t) => t.category === activeCategory)

  const isPortfolioReview = selectedTemplate?.key === 'portfolio-review'

  const handleSelectTemplate = (tpl) => {
    setSelectedTemplate(tpl)
    runForm.resetFields()
  }

  const handleProviderChange = (provider) => {
    runForm.setFieldsValue({ ai_model: MODEL_OPTIONS[provider]?.[0]?.value })
  }

  const handleHoldingChange = useCallback((holdingId) => {
    if (!holdingId) return
    const h = holdings.find((hh) => hh.id === holdingId)
    if (h) {
      runForm.setFieldsValue({
        target_name: h.name,
        symbol: h.symbol || undefined,
        market: h.market,
      })
    }
  }, [holdings, runForm])

  const handleLaunch = async () => {
    let values = {}
    if (!isPortfolioReview) {
      try {
        values = await runForm.validateFields()
      } catch {
        return
      }
    } else {
      values = runForm.getFieldsValue()
    }
    setLaunching(true)
    try {
      const payload = {
        template_key: selectedTemplate.key,
        target_name: values.target_name || null,
        symbol: values.symbol || null,
        market: values.market || null,
        related_holding_id: values.related_holding_id ? Number(values.related_holding_id) : null,
        report_language: values.report_language || 'zh',
        ai_provider: values.ai_provider || 'deepseek',
        ai_model: values.ai_model || MODEL_OPTIONS[values.ai_provider || 'deepseek']?.[0]?.value,
        extra_instruction: values.extra_instruction || null,
        use_web_search: values.use_web_search !== false,
      }
      const report = await createResearchRun(payload)
      message.success('AI 研究任务已启动，正在后台处理…')
      setReports((prev) => [report, ...prev])
      setViewReport(report)
      await refreshReports()
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
      refreshReports()
    } finally {
      setLaunching(false)
    }
  }

  const handleRefresh = async (report) => {
    try {
      const updated = await refreshResearchRun(report.id)
      setReports((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      if (viewReport?.id === updated.id) setViewReport(updated)
    } catch (e) {
      message.error('刷新失败：' + e.message)
    }
  }

  const handleCancel = async (report) => {
    try {
      await cancelResearchReport(report.id)
      await refreshReports()
      message.success('已取消')
    } catch (e) {
      message.error('取消失败：' + e.message)
    }
  }

  const handleDelete = (id) => {
    Modal.confirm({
      title: '确认删除该报告？',
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
          message.error('删除失败：' + e.message)
        }
      },
    })
  }

  const handleGenerateTracking = async (report) => {
    setGeneratingTracking(true)
    try {
      const result = await generateTrackingNotes(report.id)
      if (result.reused) {
        message.info({
          content: (
            <span>
              已存在 {result.notes.length} 条跟踪事项，无需重复生成。{' '}
              <a onClick={() => navigate(`/notes?source_report_id=${report.id}`)}>查看</a>
            </span>
          ),
          duration: 6,
        })
      } else {
        message.success({
          content: (
            <span>
              已生成 {result.notes.length} 条跟踪事项。{' '}
              <a onClick={() => navigate(`/notes?source_report_id=${report.id}`)}>前往查看</a>
            </span>
          ),
          duration: 6,
        })
      }
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || ''
      message.error('生成失败：' + detail)
    } finally {
      setGeneratingTracking(false)
    }
  }

  const holdingOptions = holdings.map((h) => ({
    value: h.id,
    label: `${h.name}${h.symbol ? ` (${h.symbol})` : ''}`,
  }))

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        <RobotOutlined style={{ marginRight: 8 }} />
        AI 投研工作台
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
        选择 AI Berkshire 模板 → 注入持仓上下文 → AI 联网研究 → 自动生成并保存报告
      </Text>
      <Text type="secondary" style={{ display: 'block', fontSize: 11, marginBottom: 4 }}>
        💡 AI 调用将优先使用你在「个人资料 → AI 设置」中配置的 API Key。
      </Text>
      <Text type="secondary" style={{ display: 'block', fontSize: 11, marginBottom: 16 }}>
        Research framework adapted from{' '}
        <a href="https://github.com/xbtlin/ai-berkshire" target="_blank" rel="noreferrer">
          xbtlin/ai-berkshire
        </a>
        {' '}· MIT License
      </Text>

      <Row gutter={16}>
        {/* 左列：模板卡片 + 任务表单 */}
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title={<Space><BulbOutlined /><span>AI Berkshire Skills</span></Space>}
            style={{ marginBottom: 12 }}
            styles={{ body: { padding: '8px 12px' } }}
          >
            <Tabs
              size="small"
              activeKey={activeCategory}
              onChange={setActiveCategory}
              items={categories.map((c) => ({ key: c, label: c }))}
              style={{ marginBottom: 8 }}
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {filteredTemplates.map((tpl) => {
                const mode = SKILL_MODE[tpl.key] || '普通模式'
                return (
                  <Card
                    key={tpl.key}
                    size="small"
                    hoverable
                    onClick={() => handleSelectTemplate(tpl)}
                    style={{
                      width: 180,
                      cursor: 'pointer',
                      border: selectedTemplate?.key === tpl.key
                        ? '2px solid #1677ff'
                        : '1px solid #d9d9d9',
                    }}
                    styles={{ body: { padding: '8px 10px' } }}
                  >
                    <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                      {tpl.priority && <Tag color="red" style={{ marginRight: 4, fontSize: 10 }}>推荐</Tag>}
                      {tpl.name}
                    </div>
                    <Space size={4} style={{ marginBottom: 4, flexWrap: 'wrap' }}>
                      <Tag color={CATEGORY_COLOR[tpl.category] || 'default'} style={{ fontSize: 11 }}>
                        {tpl.category}
                      </Tag>
                      {mode !== tpl.category && (
                        <Tag color={MODE_COLOR[mode]} style={{ fontSize: 10 }}>{mode}</Tag>
                      )}
                    </Space>
                    <div style={{ fontSize: 11, color: '#888', lineHeight: 1.3 }}>
                      {tpl.description}
                    </div>
                  </Card>
                )
              })}
            </div>
          </Card>

          {selectedTemplate && (
            <Card
              size="small"
              title={
                <div>
                  <Space>
                    <FileTextOutlined />
                    <span>{selectedTemplate.name}</span>
                    <Tag color="geekblue" style={{ fontSize: 10 }}>AI Berkshire</Tag>
                  </Space>
                  {selectedTemplate.description && (
                    <div style={{ fontSize: 11, fontWeight: 400, color: '#888', marginTop: 2 }}>
                      {selectedTemplate.description}
                    </div>
                  )}
                </div>
              }
              style={{ marginBottom: 12 }}
            >
              {isPortfolioReview && (
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
                  将自动读取当前全部持仓数据，无需手动填写公司名称。
                </Text>
              )}

              <Form
                form={runForm}
                layout="vertical"
                size="small"
                initialValues={{
                  report_language: 'zh',
                  ai_provider: 'deepseek',
                  ai_model: 'deepseek-v4-pro',
                  use_web_search: true,
                }}
              >
                {!isPortfolioReview && (
                  <>
                    <Form.Item name="related_holding_id" label="关联持仓（可选）" style={{ marginBottom: 8 }}>
                      <Select
                        allowClear
                        placeholder="选择关联持仓，自动填入公司名称和代码"
                        options={holdingOptions}
                        showSearch
                        filterOption={(input, opt) =>
                          (opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
                        }
                        onChange={handleHoldingChange}
                      />
                    </Form.Item>
                    <Form.Item
                      name="target_name"
                      label="公司名称"
                      rules={[{ required: true, message: '请填写公司名称' }]}
                      style={{ marginBottom: 8 }}
                    >
                      <Input placeholder="例：腾讯控股" />
                    </Form.Item>
                    <Form.Item name="symbol" label="代码（可选）" style={{ marginBottom: 8 }}>
                      <Input placeholder="例：700.HK" />
                    </Form.Item>
                    <Row gutter={8}>
                      <Col xs={24} sm={12}>
                        <Form.Item name="market" label="市场" style={{ marginBottom: 8 }}>
                          <Select placeholder="选择市场" allowClear options={MARKET_OPTIONS} />
                        </Form.Item>
                      </Col>
                      <Col xs={24} sm={12}>
                        <Form.Item name="report_language" label="报告语言" style={{ marginBottom: 8 }}>
                          <Select options={LANG_OPTIONS} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </>
                )}

                {isPortfolioReview && (
                  <Form.Item name="report_language" label="报告语言" style={{ marginBottom: 8 }}>
                    <Select options={LANG_OPTIONS} />
                  </Form.Item>
                )}

                <Row gutter={8}>
                  <Col xs={24} sm={12}>
                    <Form.Item name="ai_provider" label="模型提供商" style={{ marginBottom: 8 }}>
                      <Select options={PROVIDER_OPTIONS} onChange={handleProviderChange} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item name="ai_model" label="模型" style={{ marginBottom: 8 }}>
                      <Select options={MODEL_OPTIONS[aiProvider] || []} />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item
                  name="use_web_search"
                  label="联网搜索"
                  valuePropName="checked"
                  style={{ marginBottom: 2 }}
                >
                  <Switch />
                </Form.Item>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 10 }}>
                  {useWebSearch !== false
                    ? '推荐，AI 会搜索最新财报、公告和新闻'
                    : '仅使用平台上下文和模型知识'}
                </Text>

                <Form.Item name="extra_instruction" label="额外要求（可选）" style={{ marginBottom: 8 }}>
                  <TextArea rows={2} placeholder="补充研究重点或特殊要求…" />
                </Form.Item>
              </Form>

              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={launching}
                onClick={handleLaunch}
                style={{ marginTop: 4 }}
                size="middle"
              >
                {launching ? '研究中...' : '开始 AI 研究'}
              </Button>
            </Card>
          )}
        </Col>

        {/* 右列：报告详情 / 报告列表 */}
        <Col xs={24} lg={10}>
          {viewReport ? (
            <ReportDetail
              report={viewReport}
              onBack={() => setViewReport(null)}
              onRefresh={handleRefresh}
              onCancel={handleCancel}
              onDelete={handleDelete}
              onRetry={() => setViewReport(null)}
              onGenerateTracking={handleGenerateTracking}
              generatingTracking={generatingTracking}
            />
          ) : (
            <ReportList
              reports={reports}
              onSelect={setViewReport}
              onRefresh={handleRefresh}
              onDelete={handleDelete}
            />
          )}
        </Col>
      </Row>
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
        <Empty description="暂无报告，点击「开始 AI 研究」自动生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {reports.map((r) => {
            const st = STATUS_CONFIG[r.status] || STATUS_CONFIG.draft
            const isActive = r.status === 'running' || r.status === 'queued'
            return (
              <Card
                key={r.id}
                size="small"
                hoverable
                onClick={() => onSelect(r)}
                styles={{ body: { padding: '8px 10px' } }}
                style={{ cursor: 'pointer' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title || r.target_name}
                    </div>
                    <Space style={{ marginTop: 4 }} size={4}>
                      <Badge status={st.color === 'success' ? 'success' : st.color === 'error' ? 'error' : st.color === 'processing' ? 'processing' : 'default'} />
                      <Tag color={st.color} style={{ fontSize: 11 }}>
                        {st.icon && <span style={{ marginRight: 4 }}>{st.icon}</span>}
                        {st.text}
                      </Tag>
                      {r.report_language && (
                        <Tag style={{ fontSize: 10 }}>{r.report_language === 'en' ? 'EN' : '中文'}</Tag>
                      )}
                      {r.provider && <Tag style={{ fontSize: 10 }}>{r.provider}</Tag>}
                      <Text type="secondary" style={{ fontSize: 11 }}>{r.updated_at?.slice(0, 10)}</Text>
                    </Space>
                  </div>
                  <Space size={4} style={{ flexShrink: 0, marginLeft: 8 }} onClick={(e) => e.stopPropagation()}>
                    {isActive && (
                      <Tooltip title="刷新状态">
                        <Button size="small" icon={<ReloadOutlined />} onClick={() => onRefresh(r)} />
                      </Tooltip>
                    )}
                    <Tooltip title="删除">
                      <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(r.id)} />
                    </Tooltip>
                  </Space>
                </div>
                {r.report_md && (
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.report_md.slice(0, 80)}…
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

function ReportDetail({ report, onBack, onRefresh, onCancel, onDelete, onRetry, onGenerateTracking, generatingTracking }) {
  const st = STATUS_CONFIG[report.status] || STATUS_CONFIG.draft
  const isActive = report.status === 'running' || report.status === 'queued'
  const showSteps = ['queued', 'running', 'completed', 'failed'].includes(report.status)
  const sources = (() => {
    try { return JSON.parse(report.sources_json || '[]') } catch { return [] }
  })()
  const disclaimer = report.report_language === 'en' ? DISCLAIMER_EN : DISCLAIMER_ZH

  return (
    <Card
      size="small"
      title={
        <Space>
          <Button size="small" onClick={onBack}>← 返回</Button>
          <span style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }}>
            {report.title || report.target_name}
          </span>
        </Space>
      }
      extra={
        <Space size={4}>
          {isActive && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => onRefresh(report)}>刷新</Button>
          )}
          {isActive && (
            <Button size="small" danger onClick={() => onCancel(report)}>取消</Button>
          )}
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(report.id)} />
        </Space>
      }
      styles={{ body: { padding: '10px 12px' } }}
    >
      {/* Status row */}
      <Space size={6} style={{ marginBottom: 10, flexWrap: 'wrap' }}>
        <Tag color={st.color}>
          {st.icon && <span style={{ marginRight: 4 }}>{st.icon}</span>}
          {st.text}
        </Tag>
        <Tag>{report.report_language === 'en' ? 'English Report' : '中文报告'}</Tag>
        {report.provider && <Tag color="cyan">{report.provider}</Tag>}
        {report.model && <Tag color="geekblue">{report.model}</Tag>}
        {report.template_key && <Tag color="purple">{report.template_key}</Tag>}
        <Text type="secondary" style={{ fontSize: 11 }}>{report.updated_at?.slice(0, 16)}</Text>
      </Space>

      {/* Run steps progress */}
      {showSteps && (
        <Steps
          size="small"
          current={getStepCurrent(report.status)}
          status={getStepStatus(report.status)}
          items={RUN_STEPS.map((title) => ({ title }))}
          style={{ marginBottom: 12 }}
        />
      )}

      {/* Running indicator */}
      {isActive && (
        <Alert
          type="info"
          showIcon
          icon={<Spin size="small" />}
          message="AI 正在研究中，请稍候…（约 1–5 分钟，可点击「刷新」查看最新状态）"
          style={{ marginBottom: 10 }}
        />
      )}

      {/* Error */}
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

      {/* Report body */}
      {report.report_md ? (
        <div style={{
          marginBottom: 10, maxHeight: 520, overflowY: 'auto',
          padding: '4px 8px', border: '1px solid #f0f0f0', borderRadius: 6,
          background: '#fff', fontSize: 13,
        }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {report.report_md}
          </ReactMarkdown>
        </div>
      ) : (
        !isActive && report.status !== 'failed' && (
          <Empty description="暂无报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginBottom: 10 }} />
        )
      )}

      {/* Sources */}
      {sources.length > 0 ? (
        <div style={{ marginBottom: 10 }}>
          <Text strong style={{ fontSize: 12 }}><LinkOutlined /> 来源链接</Text>
          <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {sources.map((s, i) => (
              <a key={i} href={s.url} target="_blank" rel="noreferrer"
                style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                {s.title || s.url}
              </a>
            ))}
          </div>
        </div>
      ) : report.status === 'completed' && (
        <Alert type="warning" showIcon style={{ marginBottom: 10, fontSize: 11 }}
          message="该报告未返回可验证来源，请谨慎使用。" />
      )}

      {/* Disclaimer */}
      {report.report_md && (
        <Alert type="info" style={{ marginBottom: 10, fontSize: 11 }}
          message={disclaimer} />
      )}

      {/* Tracking notes */}
      {report.status === 'completed' && report.report_md && (
        <div style={{ marginBottom: 10 }}>
          <Button
            icon={<CheckCircleOutlined />}
            size="small"
            loading={generatingTracking}
            onClick={() => onGenerateTracking(report)}
          >
            生成跟踪事项
          </Button>
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
            提取报告「跟踪事项」章节，保存为投资笔记
          </Text>
        </div>
      )}

      {/* Attribution */}
      <Text type="secondary" style={{ fontSize: 10, display: 'block', marginBottom: 6 }}>
        Research framework adapted from{' '}
        <a href="https://github.com/xbtlin/ai-berkshire" target="_blank" rel="noreferrer">
          xbtlin/ai-berkshire
        </a>
        {' '}· MIT License
      </Text>

      {/* Debug panel */}
      <Collapse size="small" ghost items={[{
        key: 'debug',
        label: <Text style={{ fontSize: 11 }}>调试信息</Text>,
        children: (
          <div style={{ fontSize: 11 }}>
            {report.skill_md && (
              <div style={{ marginBottom: 8 }}>
                <Text strong>原始 Skill（AI Berkshire）</Text>
                <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
                  {report.skill_md}
                </pre>
              </div>
            )}
            {report.input_context_md && (
              <div style={{ marginBottom: 8 }}>
                <Text strong>平台上下文</Text>
                <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
                  {report.input_context_md}
                </pre>
              </div>
            )}
            {report.prompt_md && (
              <div>
                <Text strong>最终 Prompt</Text>
                <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
                  {report.prompt_md}
                </pre>
              </div>
            )}
          </div>
        ),
      }]} />
    </Card>
  )
}
