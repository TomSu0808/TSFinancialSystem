import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Empty, Form, Input, Modal, Popconfirm,
  Row, Select, Space, Tag, Tooltip, Typography, message,
} from 'antd'
import { FilterOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { listNotes, createNote, updateNote, deleteNote } from '../api'

const { Text } = Typography
const { TextArea } = Input

const NOTE_TYPES = [
  { value: 'thesis',      label: '投资逻辑', color: 'blue' },
  { value: 'risk',        label: '风险点',   color: 'red' },
  { value: 'review',      label: '复盘笔记', color: 'purple' },
  { value: 'action',      label: '待跟进',   color: 'orange' },
  { value: 'observation', label: '观察',     color: 'cyan' },
  { value: 'general',     label: '笔记',     color: 'default' },
]

const NOTE_STATUSES = [
  { value: 'active',      label: '跟踪中', color: 'green' },
  { value: 'resolved',    label: '已解决', color: 'blue' },
  { value: 'invalidated', label: '已证伪', color: 'red' },
  { value: 'archived',    label: '已归档', color: 'default' },
]

const typeConfig  = Object.fromEntries(NOTE_TYPES.map((t) => [t.value, t]))
const statusConfig = Object.fromEntries(NOTE_STATUSES.map((s) => [s.value, s]))

const fmtDate = (s) => {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function useQuery() {
  return new URLSearchParams(useLocation().search)
}

export default function Notes() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryParams = useQuery()

  const [data, setData]       = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen]       = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  // Filter state — read initial values from URL
  const [filters, setFilters] = useState({
    keyword:            queryParams.get('keyword')            || '',
    symbol:             queryParams.get('symbol')             || '',
    note_type:          queryParams.get('note_type')          || '',
    status:             queryParams.get('status')             || '',
    source_report_id:   queryParams.get('source_report_id')   ? Number(queryParams.get('source_report_id'))   : undefined,
    related_holding_id: queryParams.get('related_holding_id') ? Number(queryParams.get('related_holding_id')) : undefined,
  })
  const [filterForm] = Form.useForm()
  const initializedRef = useRef(false)

  // Sync URL → filter form on mount
  useEffect(() => {
    if (!initializedRef.current) {
      filterForm.setFieldsValue({
        keyword:   filters.keyword   || undefined,
        symbol:    filters.symbol    || undefined,
        note_type: filters.note_type || undefined,
        status:    filters.status    || undefined,
      })
      initializedRef.current = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const buildParams = (f = filters) => {
    const p = {}
    if (f.keyword)            p.keyword            = f.keyword
    if (f.symbol)             p.symbol             = f.symbol
    if (f.note_type)          p.note_type          = f.note_type
    if (f.status)             p.status             = f.status
    if (f.source_report_id)   p.source_report_id   = f.source_report_id
    if (f.related_holding_id) p.related_holding_id = f.related_holding_id
    return p
  }

  const load = async (f = filters) => {
    setLoading(true)
    try {
      setData(await listNotes(buildParams(f)))
    } catch (e) {
      message.error('加载失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // Re-load when URL query changes (e.g. navigated from Research page)
  useEffect(() => {
    const q = new URLSearchParams(location.search)
    const f = {
      keyword:            q.get('keyword')            || '',
      symbol:             q.get('symbol')             || '',
      note_type:          q.get('note_type')          || '',
      status:             q.get('status')             || '',
      source_report_id:   q.get('source_report_id')   ? Number(q.get('source_report_id'))   : undefined,
      related_holding_id: q.get('related_holding_id') ? Number(q.get('related_holding_id')) : undefined,
    }
    setFilters(f)
    filterForm.setFieldsValue({
      keyword:   f.keyword   || undefined,
      symbol:    f.symbol    || undefined,
      note_type: f.note_type || undefined,
      status:    f.status    || undefined,
    })
    load(f)
  }, [location.search]) // eslint-disable-line react-hooks/exhaustive-deps

  const applyFilters = () => {
    const vals = filterForm.getFieldsValue()
    const f = {
      keyword:   vals.keyword   || '',
      symbol:    vals.symbol    || '',
      note_type: vals.note_type || '',
      status:    vals.status    || '',
    }
    setFilters(f)
    load(f)
  }

  const resetFilters = () => {
    filterForm.resetFields()
    const f = { keyword: '', symbol: '', note_type: '', status: '' }
    setFilters(f)
    navigate('/notes')
    load(f)
  }

  // Active filter badges
  const activeFilterCount = [filters.keyword, filters.symbol, filters.note_type, filters.status, filters.source_report_id, filters.related_holding_id].filter(Boolean).length

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ note_type: 'general', status: 'active' })
    setOpen(true)
  }
  const openEdit = (record) => {
    setEditing(record)
    form.setFieldsValue(record)
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) await updateNote(editing.id, values)
      else await createNote(values)
      message.success('已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + e.message)
    }
  }

  const remove = async (id) => {
    try {
      await deleteNote(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  // Indicator when filter is from URL (e.g. source_report_id)
  const hasUrlFilter = filters.source_report_id || filters.related_holding_id

  return (
    <Card
      title={
        <Space>
          <span>投资笔记</span>
          {activeFilterCount > 0 && (
            <Tag color="blue">{activeFilterCount} 个筛选条件</Tag>
          )}
        </Space>
      }
      extra={
        <Space size={[8, 6]} wrap>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增</Button>
        </Space>
      }
    >
      {/* Filter bar */}
      <Form
        form={filterForm}
        layout="inline"
        size="small"
        style={{ marginBottom: 12, flexWrap: 'wrap', gap: '6px 0' }}
        onFinish={applyFilters}
      >
        <Form.Item name="keyword" style={{ marginBottom: 6 }}>
          <Input placeholder="关键词（标题/内容）" style={{ width: 160 }} allowClear />
        </Form.Item>
        <Form.Item name="symbol" style={{ marginBottom: 6 }}>
          <Input placeholder="标的代码" style={{ width: 110 }} allowClear />
        </Form.Item>
        <Form.Item name="note_type" style={{ marginBottom: 6 }}>
          <Select placeholder="类型" style={{ width: 110 }} allowClear
            options={NOTE_TYPES.map((t) => ({ value: t.value, label: t.label }))}
          />
        </Form.Item>
        <Form.Item name="status" style={{ marginBottom: 6 }}>
          <Select placeholder="状态" style={{ width: 110 }} allowClear
            options={NOTE_STATUSES.map((s) => ({ value: s.value, label: s.label }))}
          />
        </Form.Item>
        <Form.Item style={{ marginBottom: 6 }}>
          <Space size={4}>
            <Button htmlType="submit" icon={<FilterOutlined />} type="primary">查询</Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Form.Item>
      </Form>

      {hasUrlFilter && (
        <div style={{ marginBottom: 10, fontSize: 12, color: '#888' }}>
          {filters.source_report_id && <span>来源报告 #{filters.source_report_id} · </span>}
          {filters.related_holding_id && <span>关联持仓 #{filters.related_holding_id} · </span>}
          <a onClick={resetFilters}>清除</a>
        </div>
      )}

      <div style={{ marginBottom: 8, color: '#888', fontSize: 12 }}>共 {data.length} 条记录</div>

      {data.length === 0 && !loading ? (
        <Empty description="暂无记录，点右上角「新增」记录投资逻辑、风险、复盘、观察或待跟进事项" />
      ) : (
        <Row gutter={[12, 12]}>
          {data.map((note) => {
            const tc = typeConfig[note.note_type]   || typeConfig.general
            const sc = statusConfig[note.status]    || statusConfig.active
            return (
              <Col xs={24} sm={12} lg={8} key={note.id}>
                <Card
                  size="small"
                  title={
                    <Space size={4} style={{ flexWrap: 'wrap' }}>
                      <Tag color={tc.color} style={{ fontSize: 11 }}>{tc.label}</Tag>
                      <Tag color={sc.color} style={{ fontSize: 11 }}>{sc.label}</Tag>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{note.title || '（无标题）'}</span>
                    </Space>
                  }
                  extra={
                    <Space size={4}>
                      <a onClick={() => openEdit(note)}>编辑</a>
                      <Popconfirm title="删除这条记录？" onConfirm={() => remove(note.id)}>
                        <a style={{ color: '#cf1322' }}>删除</a>
                      </Popconfirm>
                    </Space>
                  }
                  styles={{ body: { minHeight: 80 } }}
                >
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginBottom: 8 }}>
                    {note.content.length > 200 ? note.content.slice(0, 200) + '…' : note.content}
                  </div>
                  <Space size={4} style={{ flexWrap: 'wrap' }}>
                    {note.symbol && <Tag style={{ fontSize: 11 }}>{note.symbol}</Tag>}
                    {note.tags && note.tags.split(',').filter(Boolean).map((t, i) => (
                      <Tag key={i} style={{ fontSize: 11, color: '#888' }}>{t.trim()}</Tag>
                    ))}
                    {note.source_report_id && (
                      <Tooltip title={`来自报告 #${note.source_report_id}`}>
                        <Tag style={{ fontSize: 11 }}>📊 报告</Tag>
                      </Tooltip>
                    )}
                  </Space>
                  <div style={{ marginTop: 8, color: '#bbb', fontSize: 11, textAlign: 'right' }}>
                    {fmtDate(note.updated_at)}
                  </div>
                </Card>
              </Col>
            )
          })}
        </Row>
      )}

      {/* Create / Edit modal */}
      <Modal
        title={editing ? '编辑记录' : '新增记录'}
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnHidden
        width={580}
      >
        <Form form={form} layout="vertical" size="small">
          <Form.Item name="title" label="标题（可选）">
            <Input placeholder="简短标题" />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请填写内容' }]}>
            <TextArea rows={6} placeholder="记录投资逻辑、风险点、观察、复盘或待跟进事项…" />
          </Form.Item>
          <Row gutter={8}>
            <Col xs={24} sm={12}>
              <Form.Item name="note_type" label="类型">
                <Select options={NOTE_TYPES.map((t) => ({ value: t.value, label: t.label }))} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="status" label="状态">
                <Select options={NOTE_STATUSES.map((s) => ({ value: s.value, label: s.label }))} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col xs={24} sm={12}>
              <Form.Item name="symbol" label="标的代码（可选）">
                <Input placeholder="如 AAPL、600519" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="tags" label="标签（逗号分隔，可选）">
                <Input placeholder="如 成长股,科技" />
              </Form.Item>
            </Col>
          </Row>
          <Text type="secondary" style={{ fontSize: 11 }}>
            关联持仓和来源报告可从持仓页「投资笔记」或投研页「生成跟踪事项」自动填入。
          </Text>
        </Form>
      </Modal>
    </Card>
  )
}
