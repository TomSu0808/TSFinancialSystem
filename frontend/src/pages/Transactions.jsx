import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Button, Card, Collapse, DatePicker, Drawer, Form, Input, InputNumber, Modal, Popconfirm,
  Radio, Select, Space, Steps, Table, Tag, Upload, message,
} from 'antd'
import { InboxOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listTransactions, createTransaction, updateTransaction, deleteTransaction,
  listPlatforms, previewTransactionImport, commitTransactionImport,
  previewImport, commitImport, getImportReconciliation, getImportDetail,
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

  // CSV import state (old)
  const [csvOpen, setCsvOpen] = useState(false)
  const [csvFile, setCsvFile] = useState(null)
  const [csvPreview, setCsvPreview] = useState(null)
  const [csvPreviewing, setCsvPreviewing] = useState(false)
  const [csvImporting, setCsvImporting] = useState(false)

  // New import wizard state
  const [importOpen, setImportOpen] = useState(false)
  const [importStep, setImportStep] = useState(0)
  const [importBroker, setImportBroker] = useState('futu')
  const [importPlatformId, setImportPlatformId] = useState(null)
  const [importFile, setImportFile] = useState(null)
  const [importSessionId, setImportSessionId] = useState(null)
  const [importPreview, setImportPreview] = useState(null)
  const [importPreviewing, setImportPreviewing] = useState(false)
  const [importCommitting, setImportCommitting] = useState(false)
  const [importRecon, setImportRecon] = useState(null)
  const [importFields, setImportFields] = useState({})

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

  // ── New import wizard ──────────────────────────────────────────────────────
  const openImportWizard = () => {
    setImportStep(0)
    setImportBroker('futu')
    setImportPlatformId(null)
    setImportFile(null)
    setImportSessionId(null)
    setImportPreview(null)
    setImportRecon(null)
    setImportFields({})
    setImportOpen(true)
  }

  const handleImportFile = async (file) => {
    setImportFile(file)
    setImportPreviewing(true)
    setImportPreview(null)
    try {
      const result = await previewImport(file, {
        platform_id: importPlatformId,
        broker_type: importBroker,
      })
      setImportSessionId(result.import_session_id)
      setImportPreview(result)
      setImportFields(result.detected_fields || {})
      setImportStep(2)
    } catch (e) {
      message.error('解析失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setImportPreviewing(false)
    }
    return false
  }

  const handleImportCommit = async () => {
    if (!importSessionId) return
    setImportCommitting(true)
    try {
      const result = await commitImport(importSessionId, {})
      message.success(`已成功导入 ${result.created_count} 条交易`)
      // Load reconciliation
      try {
        const recon = await getImportReconciliation(importSessionId)
        setImportRecon(recon)
      } catch (e) {
        // reconciliation may not be available
      }
      setImportStep(3)
      load()
    } catch (e) {
      message.error('导入失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setImportCommitting(false)
    }
  }

  const importPreviewColumns = [
    { title: '行', dataIndex: 'row_number', width: 50 },
    {
      title: '状态', dataIndex: 'status', width: 70,
      render: (v) => {
        const color = v === 'valid' ? 'green' : v === 'warning' ? 'orange' : v === 'duplicate' ? 'default' : 'red'
        const label = v === 'valid' ? '✓' : v === 'warning' ? '⚠' : v === 'duplicate' ? '重' : '✗'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '交易内容',
      render: (_, r) => {
        const d = r.data || {}
        return (
          <Space size={4} wrap>
            <span style={{ fontSize: 12 }}>{d.date}</span>
            <Tag style={{ fontSize: 11 }}>{TXN_ACTION_LABEL[d.action] || d.action}</Tag>
            <span style={{ fontSize: 12 }}>{d.name || d.symbol || '—'}</span>
            {d.symbol && <span style={{ color: '#999', fontSize: 11 }}>{d.symbol}</span>}
            {d.quantity != null && <span style={{ fontSize: 11 }}>×{d.quantity}</span>}
          </Space>
        )
      },
    },
    {
      title: '提示',
      render: (_, r) => (
        <div>
          {r.warnings?.map((w, i) => <div key={i} style={{ color: '#fa8c16', fontSize: 11 }}>{w}</div>)}
          {r.errors?.map((e, i) => <div key={i} style={{ color: '#cf1322', fontSize: 11 }}>{e}</div>)}
        </div>
      ),
    },
  ]

  const reconColumns = [
    { title: '代码', dataIndex: 'symbol', width: 100 },
    { title: '名称', dataIndex: 'name' },
    { title: '币种', dataIndex: 'currency', width: 60 },
    {
      title: '券商数量', dataIndex: 'broker_quantity', align: 'right',
      render: (v) => v != null ? fmt(v) : '—',
    },
    {
      title: '系统数量', dataIndex: 'system_quantity', align: 'right',
      render: (v) => v != null ? fmt(v) : '—',
    },
    {
      title: '差异', dataIndex: 'quantity_diff', align: 'right',
      render: (v) => v != null ? <span style={{ color: v === 0 ? '#52c41a' : '#cf1322', fontWeight: 600 }}>{fmt(v)}</span> : '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v) => {
        const color = v === 'matched' ? 'green' : v === 'warning' ? 'orange' : 'red'
        const label = v === 'matched' ? '一致' : v === 'warning' ? '偏差' : '异常'
        return <Tag color={color}>{label}</Tag>
      },
    },
  ]

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
          <Button icon={<UploadOutlined />} onClick={openImportWizard}>
            导入交易
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => { setCsvOpen(true); setCsvFile(null); setCsvPreview(null) }} style={{ display: 'none' }}>
            {/* 旧版导入（隐藏，API 仍可用）*/}
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

      {/* ── 新版导入向导 Drawer ────────────────────────────────────────────── */}
      <Drawer
        title="导入交易记录"
        open={importOpen}
        onClose={() => setImportOpen(false)}
        width={780}
        destroyOnHidden
      >
        <Steps
          current={importStep}
          size="small"
          style={{ marginBottom: 24 }}
          items={[
            { title: '选择券商' },
            { title: '上传文件' },
            { title: '预览确认' },
            { title: '完成' },
          ]}
        />

        {/* Step 0: 选择券商类型 */}
        {importStep === 0 && (
          <div>
            <div style={{ marginBottom: 16, fontWeight: 500 }}>选择券商类型</div>
            <Radio.Group
              value={importBroker}
              onChange={(e) => setImportBroker(e.target.value)}
              style={{ marginBottom: 24 }}
            >
              <Space direction="vertical">
                <Radio value="futu">
                  <b>富途证券</b> — 支持中英文 CSV 导出，自动识别列名
                </Radio>
                <Radio value="ibkr">
                  <b>IBKR (盈透证券)</b> — 支持 Activity Statement CSV
                </Radio>
                <Radio value="generic">
                  <b>通用格式</b> — 手动匹配 CSV 列到标准字段
                </Radio>
              </Space>
            </Radio.Group>
            <div style={{ marginBottom: 16, fontWeight: 500 }}>选择平台（可选）</div>
            <Select
              allowClear
              placeholder="选择对应账户平台"
              style={{ width: 300 }}
              value={importPlatformId}
              onChange={setImportPlatformId}
              options={platforms.map((p) => ({ value: p.id, label: p.name }))}
            />
            <div style={{ marginTop: 24 }}>
              <Button type="primary" onClick={() => setImportStep(1)}>
                下一步
              </Button>
            </div>
          </div>
        )}

        {/* Step 1: 上传文件 */}
        {importStep === 1 && (
          <div>
            <Upload.Dragger
              accept=".csv"
              maxCount={1}
              beforeUpload={handleImportFile}
              showUploadList={false}
            >
              <p style={{ margin: '8px 0 4px' }}>
                <InboxOutlined style={{ fontSize: 32, color: '#1677ff' }} />
              </p>
              <p style={{ margin: '0 0 4px', color: '#333' }}>点击或拖拽 CSV 文件到此处</p>
              {importFile && (
                <p style={{ margin: 0, color: '#1677ff', fontSize: 12 }}>{importFile.name}</p>
              )}
            </Upload.Dragger>
            {importPreviewing && (
              <div style={{ textAlign: 'center', padding: '16px 0', color: '#888' }}>解析中…</div>
            )}
            <div style={{ marginTop: 16 }}>
              <Button onClick={() => setImportStep(0)}>上一步</Button>
            </div>
          </div>
        )}

        {/* Step 2: 预览 */}
        {importStep === 2 && importPreview && (
          <div>
            {/* 字段映射摘要 */}
            {Object.keys(importFields).length > 0 && (
              <Collapse
                size="small"
                style={{ marginBottom: 12 }}
                items={[{
                  key: 'fields', label: '识别的字段映射',
                  children: (
                    <div style={{ fontSize: 12 }}>
                      {Object.entries(importFields).map(([k, v]) => (
                        <Tag key={k} style={{ marginBottom: 4 }}>
                          {k} ← {v || '未识别'}
                        </Tag>
                      ))}
                    </div>
                  ),
                }]}
              />
            )}

            {/* Summary */}
            <Space style={{ marginBottom: 12 }} wrap>
              <span style={{ color: '#555' }}>共 <b>{importPreview.summary?.total}</b> 行</span>
              <Tag color="green">可导入 {importPreview.summary?.valid} 行</Tag>
              {importPreview.summary?.warning > 0 && (
                <Tag color="orange">警告 {importPreview.summary.warning} 行</Tag>
              )}
              {importPreview.summary?.duplicate > 0 && (
                <Tag color="default">重复 {importPreview.summary.duplicate} 行</Tag>
              )}
              {importPreview.summary?.error > 0 && (
                <Tag color="red">错误 {importPreview.summary.error} 行</Tag>
              )}
            </Space>

            <Table
              dataSource={importPreview.rows}
              rowKey="row_number"
              size="small"
              pagination={{ pageSize: 15, hideOnSinglePage: true }}
              columns={importPreviewColumns}
              rowClassName={(r) => {
                if (r.status === 'error') return 'ant-table-row-danger'
                if (r.status === 'duplicate') return 'ant-table-row-warning'
                return ''
              }}
              style={{ maxHeight: 400, overflow: 'auto' }}
            />

            <div style={{ marginTop: 16 }}>
              <Space>
                <Button onClick={() => { setImportStep(1); setImportPreview(null) }}>重新上传</Button>
                <Button
                  type="primary"
                  onClick={handleImportCommit}
                  loading={importCommitting}
                  disabled={importPreview.summary?.valid === 0}
                >
                  确认导入（{importPreview.summary?.valid || 0} 条）
                </Button>
              </Space>
            </div>
          </div>
        )}

        {/* Step 3: 导入结果 + 对账 */}
        {importStep === 3 && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Tag color="green" style={{ fontSize: 14, padding: '4px 12px' }}>
                导入完成
              </Tag>
              <span style={{ marginLeft: 8, color: '#555' }}>
                交易已写入系统，持仓已同步更新
              </span>
            </div>

            {importRecon ? (
              <div>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  对账结果：共 {importRecon.total_items} 项，
                  <Tag color="green" style={{ marginLeft: 8 }}>{importRecon.matched_count} 一致</Tag>
                  {importRecon.warning_count > 0 && (
                    <Tag color="orange">{importRecon.warning_count} 偏差</Tag>
                  )}
                  {importRecon.error_count > 0 && (
                    <Tag color="red">{importRecon.error_count} 异常</Tag>
                  )}
                </div>
                <Table
                  dataSource={importRecon.items}
                  rowKey="symbol"
                  size="small"
                  pagination={false}
                  columns={reconColumns}
                  scroll={{ x: 700 }}
                  style={{ marginTop: 12 }}
                />
              </div>
            ) : (
              <div style={{ color: '#888' }}>
                未生成对账数据（可能因为导入文件中无持仓信息）
              </div>
            )}

            <div style={{ marginTop: 24 }}>
              <Space>
                <Button type="primary" onClick={() => { setImportOpen(false); load() }}>
                  完成
                </Button>
                <Button onClick={() => {
                  setImportStep(0)
                  setImportFile(null)
                  setImportSessionId(null)
                  setImportPreview(null)
                  setImportRecon(null)
                }}>
                  再导入一份
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Drawer>

      {/* CSV 导入 Modal（旧版，保留兼容）*/}
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
