import { useCallback, useEffect, useState } from 'react'
import {
  Badge, Button, Card, Col, Empty, Form, Input, InputNumber, Popconfirm,
  Row, Select, Space, Switch, Table, Tabs, Tag, message,
} from 'antd'
import { BellOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  listAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
  listAlertEvents, markEventRead, markAllRead, dismissEvent, evaluateAlerts,
  listHoldings,
} from '../api'

const ALERT_TYPE_OPTIONS = [
  { value: 'price_above', label: '价格高于阈值' },
  { value: 'price_below', label: '价格低于阈值' },
  { value: 'day_change_pct_above', label: '今日涨幅高于（%）' },
  { value: 'day_change_pct_below', label: '今日跌幅低于（%）' },
  { value: 'allocation_above', label: '仓位占比高于（%）' },
  { value: 'allocation_below', label: '仓位占比低于（%）' },
  { value: 'price_stale', label: '行情过期未更新' },
  { value: 'refresh_failed', label: '自动刷新失败' },
]

const SEVERITY_COLOR = { info: 'blue', warning: 'orange', critical: 'red' }
const SEVERITY_LABEL = { info: '提示', warning: '注意', critical: '重要' }
const STATUS_COLOR = { unread: 'processing', read: 'default', dismissed: 'default' }
const STATUS_LABEL = { unread: '未读', read: '已读', dismissed: '已忽略' }

const typeLabel = (t) => ALERT_TYPE_OPTIONS.find((o) => o.value === t)?.label || t

function RulesTab() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [holdings, setHoldings] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editRule, setEditRule] = useState(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [r, h] = await Promise.all([listAlertRules(), listHoldings()])
      setRules(r)
      setHoldings(h)
    } catch (e) {
      message.error('加载失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditRule(null)
    form.resetFields()
    form.setFieldsValue({ enabled: true, alert_type: 'price_above' })
    setShowForm(true)
  }

  const openEdit = (rule) => {
    setEditRule(rule)
    form.setFieldsValue({
      name: rule.name,
      alert_type: rule.alert_type,
      enabled: rule.enabled,
      holding_id: rule.holding_id,
      symbol: rule.symbol,
      threshold_value: rule.threshold_value,
      stale_hours: rule.stale_hours,
    })
    setShowForm(true)
  }

  const handleSave = async () => {
    let values
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    // strip null-ish
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v !== undefined && v !== null && v !== '')
    )
    setSaving(true)
    try {
      if (editRule) {
        await updateAlertRule(editRule.id, payload)
        message.success('已更新')
      } else {
        await createAlertRule(payload)
        message.success('已创建')
      }
      setShowForm(false)
      load()
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteAlertRule(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  const toggleEnabled = async (rule) => {
    try {
      await updateAlertRule(rule.id, { enabled: !rule.enabled })
      load()
    } catch (e) {
      message.error('操作失败：' + e.message)
    }
  }

  const alertType = Form.useWatch('alert_type', form)
  const needsThreshold = alertType && !['price_stale', 'refresh_failed'].includes(alertType)
  const needsStaleHours = alertType === 'price_stale'

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      render: (t) => <Tag>{typeLabel(t)}</Tag>,
    },
    {
      title: '标的/条件',
      key: 'target',
      render: (_, r) => (
        <Space size={4} wrap>
          {r.symbol && <Tag color="blue">{r.symbol}</Tag>}
          {r.holding_id && <Tag color="geekblue">持仓#{r.holding_id}</Tag>}
          {r.threshold_value != null && <span>阈值：{r.threshold_value}</span>}
          {r.stale_hours != null && <span>{r.stale_hours}h</span>}
        </Space>
      ),
    },
    {
      title: '启用',
      key: 'enabled',
      render: (_, r) => (
        <Switch size="small" checked={r.enabled} onChange={() => toggleEnabled(r)} />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" type="link" onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm
            title="确认删除此规则？"
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => handleDelete(r.id)}
          >
            <Button size="small" type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" style={{ display: 'flex' }} size={12}>
      <Row justify="space-between" align="middle">
        <Col>
          <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>
            新建规则
          </Button>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        </Col>
      </Row>

      {showForm && (
        <Card size="small" title={editRule ? '编辑规则' : '新建规则'} style={{ borderColor: '#1677ff33' }}>
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="如：AAPL 价格提醒" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="alert_type" label="提醒类型" rules={[{ required: true }]}>
                  <Select options={ALERT_TYPE_OPTIONS} placeholder="选择类型" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="holding_id" label="关联持仓（可选）">
                  <Select
                    allowClear
                    showSearch
                    placeholder="选择持仓"
                    filterOption={(input, opt) =>
                      opt.label?.toLowerCase().includes(input.toLowerCase())
                    }
                    options={holdings.map((h) => ({
                      value: h.id,
                      label: `${h.name || h.symbol} (${h.symbol})`,
                    }))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="symbol" label="标的代码（可选，无持仓时用）">
                  <Input placeholder="如 AAPL" />
                </Form.Item>
              </Col>
              {needsThreshold && (
                <Col xs={24} sm={12}>
                  <Form.Item
                    name="threshold_value"
                    label="阈值"
                    rules={[{ required: true, message: '请输入阈值' }]}
                  >
                    <InputNumber style={{ width: '100%' }} placeholder="数值" />
                  </Form.Item>
                </Col>
              )}
              {needsStaleHours && (
                <Col xs={24} sm={12}>
                  <Form.Item name="stale_hours" label="过期阈值（小时）">
                    <InputNumber style={{ width: '100%' }} min={1} placeholder="24" />
                  </Form.Item>
                </Col>
              )}
              <Col xs={24} sm={12}>
                <Form.Item name="enabled" label="启用" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            <Space>
              <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
              <Button onClick={() => setShowForm(false)}>取消</Button>
            </Space>
          </Form>
        </Card>
      )}

      <Table
        dataSource={rules}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={false}
        locale={{ emptyText: <Empty description="暂无提醒规则，点击「新建规则」添加" /> }}
      />
    </Space>
  )
}

function EventsTab() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('unread')
  const [evaluating, setEvaluating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = statusFilter ? { status: statusFilter } : {}
      setEvents(await listAlertEvents(params))
    } catch (e) {
      message.error('加载失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const handleRead = async (id) => {
    try { await markEventRead(id); load() } catch (e) { message.error(e.message) }
  }
  const handleDismiss = async (id) => {
    try { await dismissEvent(id); load() } catch (e) { message.error(e.message) }
  }
  const handleMarkAllRead = async () => {
    try {
      const r = await markAllRead()
      message.success(`已标记 ${r.updated} 条已读`)
      load()
    } catch (e) { message.error(e.message) }
  }
  const handleEvaluate = async () => {
    setEvaluating(true)
    try {
      const r = await evaluateAlerts()
      message.success(r.triggered > 0 ? `触发 ${r.triggered} 条新提醒` : '无新提醒')
      load()
    } catch (e) {
      message.error('评估失败：' + e.message)
    } finally {
      setEvaluating(false)
    }
  }

  const columns = [
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      width: 72,
      render: (s) => <Tag color={SEVERITY_COLOR[s] || 'default'}>{SEVERITY_LABEL[s] || s}</Tag>,
    },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '内容', dataIndex: 'message', key: 'message', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 72,
      render: (s) => <Badge status={STATUS_COLOR[s]} text={STATUS_LABEL[s]} />,
    },
    {
      title: '时间',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      width: 120,
      render: (t) => t ? new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, r) => (
        <Space size={4}>
          {r.status === 'unread' && (
            <Button size="small" type="link" onClick={() => handleRead(r.id)}>已读</Button>
          )}
          {r.status !== 'dismissed' && (
            <Button size="small" type="link" danger onClick={() => handleDismiss(r.id)}>忽略</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" style={{ display: 'flex' }} size={12}>
      <Row justify="space-between" align="middle" wrap>
        <Col>
          <Space>
            <Select
              value={statusFilter}
              onChange={(v) => setStatusFilter(v)}
              style={{ width: 120 }}
              options={[
                { value: '', label: '全部' },
                { value: 'unread', label: '未读' },
                { value: 'read', label: '已读' },
                { value: 'dismissed', label: '已忽略' },
              ]}
            />
            <Button loading={loading} icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        </Col>
        <Col>
          <Space>
            <Button onClick={handleMarkAllRead}>全部已读</Button>
            <Button
              type="primary"
              icon={<BellOutlined />}
              loading={evaluating}
              onClick={handleEvaluate}
            >
              立即评估
            </Button>
          </Space>
        </Col>
      </Row>

      <Table
        dataSource={events}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        rowClassName={(r) => r.status === 'unread' ? 'ant-table-row-selected' : ''}
        locale={{ emptyText: <Empty description="暂无提醒事件" /> }}
      />
    </Space>
  )
}

export default function Alerts() {
  return (
    <Card title={<Space><BellOutlined />提醒</Space>}>
      <Tabs
        items={[
          { key: 'events', label: '事件', children: <EventsTab /> },
          { key: 'rules', label: '规则', children: <RulesTab /> },
        ]}
      />
    </Card>
  )
}
