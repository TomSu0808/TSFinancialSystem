import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Button, Card, DatePicker, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tag, Upload, message,
} from 'antd'
import { InboxOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listTransactions, createTransaction, updateTransaction, deleteTransaction,
  listPlatforms, previewTransactionImport, commitTransactionImport,
} from '../api'
import {
  CURRENCIES, TXN_ACTIONS, TXN_ACTION_LABEL, CURRENCY_SYMBOL, fmt,
} from '../constants'

const ACTION_COLOR = {
  buy: 'red', sell: 'green', dividend: 'gold', deposit: 'blue', withdraw: 'purple', other: 'default',
}

const txnAmount = (t) => {
  if (t.amount != null) return t.amount
  if (t.quantity != null && t.price != null) {
    const gross = t.quantity * t.price
    const fee = t.fee || 0
    return t.action === 'buy' ? gross + fee : gross - fee
  }
  return null
}

const CSV_TEMPLATE = [
  'date,action,name,symbol,platform,currency,quantity,price,fee,amount,note',
  '2026-01-01,buy,Apple,AAPL,富途,USD,100,150.00,3.5,,首次买入',
].join('\n')

export default function Transactions() {
  const location = useLocation()
  const [data, setData] = useState([])
  const [platforms, setPlatforms] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()
  const [filterForm] = Form.useForm()

  // CSV import state
  const [csvOpen, setCsvOpen] = useState(false)
  const [csvFile, setCsvFile] = useState(null)
  const [csvPreview, setCsvPreview] = useState(null)
  const [csvPreviewing, setCsvPreviewing] = useState(false)
  const [csvImporting, setCsvImporting] = useState(false)

  const platName = useMemo(
    () => Object.fromEntries(platforms.map((p) => [p.id, p.name])),
    [platforms],
  )

  const load = async (f = {}) => {
    setLoading(true)
    const params = {}
    if (f.keyword) params.keyword = f.keyword
    if (f.platform_id != null) params.platform_id = f.platform_id
    if (f.action) params.action = f.action
    if (f.currency) params.currency = f.currency
    if (f.date_from) params.date_from = f.date_from
    if (f.date_to) params.date_to = f.date_to
    try {
      const [txns, plats] = await Promise.all([listTransactions(params), listPlatforms()])
      setData(txns)
      setPlatforms(plats)
    } catch (e) {
      message.error('加载交易记录失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (location.state?.openAdd) {
      openAdd()
      window.history.replaceState({}, '')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const applyFilters = () => {
    const v = filterForm.getFieldsValue()
    const dr = v.dateRange
    load({
      keyword: v.keyword || '',
      platform_id: v.platform_id ?? null,
      action: v.action || '',
      currency: v.currency || '',
      date_from: dr?.[0]?.format('YYYY-MM-DD') || '',
      date_to: dr?.[1]?.format('YYYY-MM-DD') || '',
    })
  }

  const resetFilters = () => {
    filterForm.resetFields()
    load({})
  }

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ action: 'buy', currency: 'CNY', date: dayjs() })
    setOpen(true)
  }
  const openEdit = (r) => {
    setEditing(r)
    form.setFieldsValue({ ...r, date: r.date ? dayjs(r.date) : null })
    setOpen(true)
  }

  const submit = async () => {
    const v = await form.validateFields()
    const payload = { ...v, date: v.date ? v.date.format('YYYY-MM-DD') : '' }
    try {
      if (editing) await updateTransaction(editing.id, payload)
      else await createTransaction(payload)
      const drives = ['buy', 'sell', 'dividend'].includes(payload.action)
      message.success(drives ? '已保存，相关持仓已同步' : '已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const remove = async (id) => {
    try {
      await deleteTransaction(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  // ── CSV import ──────────────────────────────────────────────────────────────
  const handleCsvPreview = async (file) => {
    setCsvFile(file)
    setCsvPreview(null)
    setCsvPreviewing(true)
    try {
      const result = await previewTransactionImport(file)
      setCsvPreview(result)
    } catch (e) {
      message.error('预览失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setCsvPreviewing(false)
    }
    return false // prevent antd auto-upload
  }

  const handleCsvCommit = async () => {
    if (!csvFile) return
    setCsvImporting(true)
    try {
      const result = await commitTransactionImport(csvFile)
      message.success(`已成功导入 ${result.imported} 条交易`)
      setCsvOpen(false)
      setCsvFile(null)
      setCsvPreview(null)
      load()
    } catch (e) {
      const detail = e.response?.data?.detail
      if (detail && typeof detail === 'object') {
        setCsvPreview(detail)
      }
      message.error('导入失败：' + (detail?.message || e.message))
    } finally {
      setCsvImporting(false)
    }
  }

  const downloadTemplate = () => {
    const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'transaction_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const previewColumns = [
    { title: '行', dataIndex: 'row_number', width: 50 },
    {
      title: '状态', dataIndex: 'valid', width: 60,
      render: (v) => <Tag color={v ? 'green' : 'red'}>{v ? '✓' : '✗'}</Tag>,
    },
    {
      title: '内容 / 错误',
      render: (_, r) => r.valid ? (
        <Space size={4} wrap>
          <span style={{ fontSize: 12 }}>{r.data?.date}</span>
          <Tag style={{ fontSize: 11 }}>{TXN_ACTION_LABEL[r.data?.action] || r.data?.action}</Tag>
          <span style={{ fontSize: 12 }}>{r.data?.name || r.data?.symbol || '—'}</span>
          {r.data?.symbol && r.data?.name && (
            <span style={{ color: '#999', fontSize: 11 }}>{r.data.symbol}</span>
          )}
        </Space>
      ) : (
        <div style={{ color: '#cf1322', fontSize: 12 }}>{r.errors?.join('；')}</div>
      ),
    },
  ]

  const columns = [
    { title: '日期', dataIndex: 'date', width: 110 },
    {
      title: '类型', dataIndex: 'action', width: 100,
      render: (v) => <Tag color={ACTION_COLOR[v]}>{TXN_ACTION_LABEL[v] || v}</Tag>,
    },
    {
      title: '标的', dataIndex: 'name',
      render: (t, r) => (
        <Space direction="vertical" size={0}>
          <span>{t || '—'}</span>
          {r.symbol ? <span style={{ color: '#999', fontSize: 12 }}>{r.symbol}</span> : null}
        </Space>
      ),
    },
    { title: '平台', dataIndex: 'platform_id', width: 110, render: (v) => platName[v] || '—' },
    { title: '数量', dataIndex: 'quantity', align: 'right', width: 90, render: (v) => (v == null ? '—' : v) },
    {
      title: '价格', dataIndex: 'price', align: 'right', width: 110,
      render: (v, r) => (v == null ? '—' : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(v)}`),
    },
    { title: '费用', dataIndex: 'fee', align: 'right', width: 90, render: (v, r) => (v == null ? '—' : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(v)}`) },
    {
      title: '金额', align: 'right', width: 130,
      render: (_, r) => {
        const a = txnAmount(r)
        return a == null ? '—' : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(a)}`
      },
    },
    { title: '备注', dataIndex: 'note', ellipsis: true },
    {
      title: '操作', width: 110, fixed: 'right',
      render: (_, r) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          <Popconfirm title="删除这条交易？" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="交易记录"
      extra={
        <Space>
          <Button icon={<UploadOutlined />} onClick={() => { setCsvOpen(true); setCsvFile(null); setCsvPreview(null) }}>
            导入 CSV
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>记一笔</Button>
        </Space>
      }
    >
      {/* 筛选栏 */}
      <Form form={filterForm} layout="inline" style={{ marginBottom: 12, rowGap: 8 }}>
        <Form.Item name="keyword" style={{ marginBottom: 0 }}>
          <Input placeholder="搜索标的、代码、备注" style={{ width: 180 }} allowClear />
        </Form.Item>
        <Form.Item name="platform_id" style={{ marginBottom: 0 }}>
          <Select
            allowClear
            placeholder="平台"
            style={{ width: 120 }}
            options={platforms.map((p) => ({ value: p.id, label: p.name }))}
          />
        </Form.Item>
        <Form.Item name="action" style={{ marginBottom: 0 }}>
          <Select allowClear placeholder="类型" style={{ width: 110 }} options={TXN_ACTIONS} />
        </Form.Item>
        <Form.Item name="currency" style={{ marginBottom: 0 }}>
          <Select allowClear placeholder="币种" style={{ width: 110 }} options={CURRENCIES} />
        </Form.Item>
        <Form.Item name="dateRange" style={{ marginBottom: 0 }}>
          <DatePicker.RangePicker style={{ width: 220 }} />
        </Form.Item>
        <Form.Item style={{ marginBottom: 0 }}>
          <Button type="primary" onClick={applyFilters}>查询</Button>
        </Form.Item>
        <Form.Item style={{ marginBottom: 0 }}>
          <Button onClick={resetFilters}>重置</Button>
        </Form.Item>
      </Form>

      <div style={{ marginBottom: 8, color: '#888', fontSize: 13 }}>
        共 {data.length} 条交易 · 买入/卖出会自动更新对应持仓（按 平台 + 代码 + 币种 匹配）；分红计入已实现收益
      </div>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        scroll={{ x: 1000 }}
        size="small"
      />

      {/* 记一笔 / 编辑 Modal */}
      <Modal
        title={editing ? '编辑交易' : '记一笔交易'}
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical">
          <Space style={{ display: 'flex' }}>
            <Form.Item name="date" label="日期" rules={[{ required: true, message: '请选日期' }]} style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="action" label="类型" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={TXN_ACTIONS} />
            </Form.Item>
            <Form.Item name="currency" label="币种" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={CURRENCIES} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="name" label="标的名称" style={{ flex: 1 }}>
              <Input placeholder="如：Apple、贵州茅台" />
            </Form.Item>
            <Form.Item name="platform_id" label="平台" style={{ flex: 1 }}>
              <Select allowClear placeholder="可选" options={platforms.map((p) => ({ value: p.id, label: p.name }))} />
            </Form.Item>
          </Space>
          <Form.Item name="symbol" label="代码（可选）">
            <Input placeholder="如 AAPL、600519" />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="quantity" label="数量" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} placeholder="股数/份额" />
            </Form.Item>
            <Form.Item name="price" label="价格" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} placeholder="成交价" />
            </Form.Item>
            <Form.Item name="fee" label="费用" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} placeholder="手续费" />
            </Form.Item>
          </Space>
          <Form.Item name="amount" label="金额（可选，留空按 量×价±费 估算）">
            <InputNumber style={{ width: '100%' }} placeholder="入金/出金/分红可直接填金额" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      {/* CSV 导入 Modal */}
      <Modal
        title="导入 CSV 交易记录"
        open={csvOpen}
        onOk={handleCsvCommit}
        okText="确认导入"
        okButtonProps={{
          disabled: !csvPreview || csvPreview.error_rows > 0 || csvPreview.valid_rows === 0,
          loading: csvImporting,
        }}
        onCancel={() => { setCsvOpen(false); setCsvFile(null); setCsvPreview(null) }}
        destroyOnHidden
        width={720}
      >
        {/* 格式说明 */}
        <div style={{ background: '#f9f9f9', padding: 12, borderRadius: 6, marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>CSV 格式说明</div>
          <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#444', wordBreak: 'break-all' }}>
            date, action, name, symbol, platform, currency, quantity, price, fee, amount, note
          </div>
          <div style={{ fontSize: 12, color: '#888', marginTop: 6, lineHeight: 1.6 }}>
            <b>date</b>：YYYY-MM-DD &nbsp;·&nbsp;
            <b>action</b>：buy / sell / dividend / deposit / withdraw / other &nbsp;·&nbsp;
            <b>platform</b>：需与账户名称完全匹配，可留空 &nbsp;·&nbsp;
            <b>currency</b>：CNY / USD / HKD，默认 CNY &nbsp;·&nbsp;
            数字字段可留空
          </div>
          <Button size="small" style={{ marginTop: 8 }} onClick={downloadTemplate}>
            下载模板
          </Button>
        </div>

        {/* 上传区 */}
        <Upload.Dragger
          accept=".csv"
          maxCount={1}
          beforeUpload={handleCsvPreview}
          showUploadList={false}
          style={{ marginBottom: 12 }}
        >
          <p style={{ margin: '8px 0 4px' }}>
            <InboxOutlined style={{ fontSize: 32, color: '#1677ff' }} />
          </p>
          <p style={{ margin: '0 0 4px', color: '#333' }}>点击或拖拽 CSV 文件到此处</p>
          {csvFile && (
            <p style={{ margin: 0, color: '#1677ff', fontSize: 12 }}>{csvFile.name}</p>
          )}
        </Upload.Dragger>

        {/* 预览结果 */}
        {csvPreviewing && (
          <div style={{ textAlign: 'center', padding: '16px 0', color: '#888' }}>解析中…</div>
        )}
        {csvPreview && !csvPreviewing && (
          <div>
            <Space style={{ marginBottom: 8 }} wrap>
              <span style={{ color: '#555' }}>共 <b>{csvPreview.total_rows}</b> 行</span>
              <Tag color="green">可导入 {csvPreview.valid_rows} 行</Tag>
              {csvPreview.error_rows > 0 && (
                <Tag color="red">错误 {csvPreview.error_rows} 行</Tag>
              )}
              {csvPreview.error_rows > 0 && (
                <span style={{ color: '#cf1322', fontSize: 12 }}>
                  请修正所有错误后重新上传
                </span>
              )}
            </Space>
            <Table
              dataSource={csvPreview.rows}
              rowKey="row_number"
              size="small"
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              columns={previewColumns}
              rowClassName={(r) => (r.valid ? '' : 'ant-table-row-danger')}
              style={{ maxHeight: 320, overflow: 'auto' }}
            />
          </div>
        )}
      </Modal>
    </Card>
  )
}
