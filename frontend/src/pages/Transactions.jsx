import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Button, Card, DatePicker, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tag, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listTransactions, createTransaction, updateTransaction, deleteTransaction, listPlatforms,
} from '../api'
import {
  CURRENCIES, TXN_ACTIONS, TXN_ACTION_LABEL, CURRENCY_SYMBOL, fmt,
} from '../constants'

const ACTION_COLOR = {
  buy: 'red', sell: 'green', dividend: 'gold', deposit: 'blue', withdraw: 'purple', other: 'default',
}

// 现金流：手填 amount 优先，否则按 数量×价格(±费) 估算
const txnAmount = (t) => {
  if (t.amount != null) return t.amount
  if (t.quantity != null && t.price != null) {
    const gross = t.quantity * t.price
    const fee = t.fee || 0
    return t.action === 'buy' ? gross + fee : gross - fee
  }
  return null
}

export default function Transactions() {
  const location = useLocation()
  const [data, setData] = useState([])
  const [platforms, setPlatforms] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const platName = useMemo(
    () => Object.fromEntries(platforms.map((p) => [p.id, p.name])),
    [platforms],
  )

  const load = async () => {
    setLoading(true)
    try {
      const [txns, plats] = await Promise.all([listTransactions(), listPlatforms()])
      setData(txns)
      setPlatforms(plats)
    } catch (e) {
      message.error('加载交易记录失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // 从仪表盘"记一笔"快捷入口跳转过来时，自动打开弹窗
  useEffect(() => {
    if (location.state?.openAdd) {
      openAdd()
      window.history.replaceState({}, '')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>记一笔</Button>}
    >
      <div style={{ marginBottom: 12, color: '#888', fontSize: 13 }}>
        买入/卖出会自动更新对应持仓（按 平台 + 代码 + 币种 匹配）的数量与移动加权成本；
        分红计入已实现收益。入金/出金/其它仅作记录。
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
    </Card>
  )
}
