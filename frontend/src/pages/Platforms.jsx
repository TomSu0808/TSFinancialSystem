import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Button, Card, Form, Input, Modal, Popconfirm, Progress, Segmented, Space, Table, Tag, message,
} from 'antd'
import { PlusOutlined, LinkOutlined } from '@ant-design/icons'
import {
  listPlatforms, createPlatform, updatePlatform, deletePlatform, listHoldings, getRate,
} from '../api'
import { CURRENCY_SYMBOL, ASSET_TYPE_LABEL, fmt } from '../constants'
import { marketValue, costBasis, profitOf, isDerived } from '../holdings'

export default function Platforms() {
  const [data, setData] = useState([])
  const [holdings, setHoldings] = useState([])
  const [rate, setRate] = useState(7.2) // USDCNY
  const [currency, setCurrency] = useState('CNY')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [plats, hs, fx] = await Promise.all([listPlatforms(), listHoldings(), getRate()])
      setData(plats)
      setHoldings(hs)
      setRate(fx.rate || 7.2)
    } catch (e) {
      message.error('加载平台失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // ---- 币种折算：本币 → 展示币种 ----
  const sym = CURRENCY_SYMBOL[currency]
  const toCny = (mv, cur) => mv * (cur === 'USD' ? rate : cur === 'HKD' ? rate / 7.8 : 1)
  const toDisplay = (cny) => (currency === 'CNY' ? cny : rate ? cny / rate : 0)
  const displayValue = (h) => toDisplay(toCny(marketValue(h), h.currency))

  // 按平台分组 + 各平台总额（展示币种）
  const byPlatform = useMemo(() => {
    const map = {}
    for (const h of holdings) {
      (map[h.platform_id] ||= []).push(h)
    }
    return map
  }, [holdings])

  const platformTotal = (pid) =>
    (byPlatform[pid] || []).reduce((s, h) => s + displayValue(h), 0)

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
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
      if (editing) await updatePlatform(editing.id, values)
      else await createPlatform(values)
      message.success('已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + e.message)
    }
  }

  const remove = async (id) => {
    try {
      await deletePlatform(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  // ---- 展开行：该平台下的资产明细 ----
  const expandedRowRender = (platform) => {
    const total = platformTotal(platform.id)
    const rows = (byPlatform[platform.id] || [])
      .slice()
      .sort((a, b) => displayValue(b) - displayValue(a))

    const subColumns = [
      {
        title: '名称', dataIndex: 'name',
        render: (t, r) => (
          <Space direction="vertical" size={0}>
            <Space size={4}>
              <span>{t || '（未命名）'}</span>
              {isDerived(r) && <Tag color="blue" icon={<LinkOutlined />} style={{ marginInlineStart: 0 }}>流水</Tag>}
            </Space>
            <span style={{ color: '#999', fontSize: 12 }}>
              {[ASSET_TYPE_LABEL[r.asset_type], r.symbol].filter(Boolean).join(' · ')}
            </span>
          </Space>
        ),
      },
      {
        title: '现价', align: 'right', width: 130,
        render: (_, r) => (r.current_price == null
          ? '—'
          : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(r.current_price)}`),
      },
      {
        title: `市值（${sym}）`, align: 'right', width: 150,
        render: (_, r) => `${sym}${fmt(displayValue(r))}`,
      },
      {
        title: '盈亏', align: 'right', width: 140,
        render: (_, r) => {
          const p = profitOf(r)
          if (p == null) return '—'
          const cb = costBasis(r)
          const pct = cb ? (p / cb) * 100 : 0
          const up = p >= 0
          return (
            <span style={{ color: up ? '#cf1322' : '#3f8600' }}>
              {up ? '+' : ''}{CURRENCY_SYMBOL[r.currency] || ''}{fmt(p)}
              <span style={{ fontSize: 12, marginLeft: 4 }}>({up ? '+' : ''}{pct.toFixed(1)}%)</span>
            </span>
          )
        },
      },
      {
        title: '仓位比例', width: 180,
        render: (_, r) => {
          const pct = total ? (displayValue(r) / total) * 100 : 0
          return <Progress percent={Number(pct.toFixed(1))} size="small" status="normal" />
        },
      },
    ]

    return (
      <Table
        rowKey="id"
        dataSource={rows}
        columns={subColumns}
        pagination={false}
        size="small"
      />
    )
  }

  const columns = [
    {
      title: '平台',
      dataIndex: 'name',
      render: (text, r) => <Link to={`/platforms/${r.id}`}>{text}</Link>,
    },
    {
      title: `总额（${sym}）`,
      align: 'right',
      width: 180,
      sorter: (a, b) => platformTotal(a.id) - platformTotal(b.id),
      render: (_, r) => <strong>{sym}{fmt(platformTotal(r.id))}</strong>,
    },
    { title: '备注', dataIndex: 'note' },
    {
      title: '操作',
      width: 220,
      render: (_, r) => (
        <Space>
          <Link to={`/platforms/${r.id}`}>管理资产</Link>
          <a onClick={() => openEdit(r)}>编辑</a>
          <Popconfirm title="删除平台及其下所有资产？" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="平台管理"
      extra={
        <Space>
          <Tag>汇率 USD/CNY: {rate}</Tag>
          <Segmented
            value={currency}
            onChange={setCurrency}
            options={[
              { label: '¥ 人民币', value: 'CNY' },
              { label: '$ 美元', value: 'USD' },
            ]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
            添加平台
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        pagination={false}
        expandable={{
          expandedRowRender,
          rowExpandable: (r) => (byPlatform[r.id] || []).length > 0,
        }}
      />

      <Modal title={editing ? '编辑平台' : '添加平台'} open={open} onOk={submit} onCancel={() => setOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="平台名称" rules={[{ required: true, message: '请输入平台名称' }]}>
            <Input placeholder="如：富途、盈透 IBKR、老虎证券…" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
