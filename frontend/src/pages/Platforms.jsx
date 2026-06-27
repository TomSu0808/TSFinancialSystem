import { useEffect, useMemo, useState } from 'react'
import { useColorScheme } from '../colorScheme.jsx'
import { useDisplaySettings, convertAmount } from '../displaySettings.jsx'
import { Link } from 'react-router-dom'
import {
  Button, Card, Col, Empty, Form, Input, Modal, Popconfirm, Progress, Row, Segmented, Space, Table, Tag, message,
} from 'antd'
import { PlusOutlined, LinkOutlined, ArrowRightOutlined } from '@ant-design/icons'
import {
  listPlatforms, createPlatform, updatePlatform, deletePlatform, listHoldings, getRate,
} from '../api'
import { CURRENCY_SYMBOL, ASSET_TYPE_LABEL, fmt } from '../constants'
import { marketValue, costBasis, profitOf, isDerived } from '../holdings'

export default function Platforms() {
  const { upColor, downColor } = useColorScheme()
  const { displayCurrency, setDisplayCurrency } = useDisplaySettings()
  const [data, setData] = useState([])
  const [holdings, setHoldings] = useState([])
  const [fx, setFx] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [plats, hs, fxRate] = await Promise.all([listPlatforms(), listHoldings(), getRate()])
      setData(plats)
      setHoldings(hs)
      setFx(fxRate)
    } catch (e) {
      message.error('加载账户失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const sym = CURRENCY_SYMBOL[displayCurrency]
  const rate = fx?.updated_at ? fx.rate : null
  const displayValue = (h) => convertAmount(marketValue(h), h.currency, displayCurrency, rate) ?? 0

  const byPlatform = useMemo(() => {
    const map = {}
    for (const h of holdings) {
      (map[h.platform_id] ||= []).push(h)
    }
    return map
  }, [holdings])

  const platformTotal = (pid) =>
    (byPlatform[pid] || []).reduce((s, h) => s + displayValue(h), 0)

  const grandTotal = data.reduce((sum, p) => sum + platformTotal(p.id), 0)

  const accountCards = data
    .map((p) => {
      const rows = byPlatform[p.id] || []
      const total = platformTotal(p.id)
      const topHolding = rows.slice().sort((a, b) => displayValue(b) - displayValue(a))[0]
      return {
        ...p,
        total,
        holdingCount: rows.length,
        pct: grandTotal ? total / grandTotal * 100 : 0,
        topHolding,
      }
    })
    .sort((a, b) => b.total - a.total)

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

  const expandedRowRender = (platform) => {
    const total = platformTotal(platform.id)
    const rows = (byPlatform[platform.id] || [])
      .slice()
      .sort((a, b) => displayValue(b) - displayValue(a))

    const subColumns = [
      {
        title: '名称',
        dataIndex: 'name',
        render: (t, r) => (
          <Space direction="vertical" size={0}>
            <Space size={4}>
              <span>{t || '未命名资产'}</span>
              {isDerived(r) && <Tag color="blue" icon={<LinkOutlined />} style={{ marginInlineStart: 0 }}>流水</Tag>}
            </Space>
            <span style={{ color: '#999', fontSize: 12 }}>
              {[ASSET_TYPE_LABEL[r.asset_type], r.symbol].filter(Boolean).join(' · ')}
            </span>
          </Space>
        ),
      },
      {
        title: '现价',
        align: 'right',
        width: 130,
        render: (_, r) => (r.current_price == null
          ? '—'
          : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(r.current_price)}`),
      },
      {
        title: `市值（${sym}）`,
        align: 'right',
        width: 150,
        render: (_, r) => `${sym}${fmt(displayValue(r))}`,
      },
      {
        title: '盈亏',
        align: 'right',
        width: 140,
        render: (_, r) => {
          const p = profitOf(r)
          if (p == null) return '—'
          const cb = costBasis(r)
          const pct = cb ? (p / cb) * 100 : 0
          const up = p >= 0
          const displayP = convertAmount(p, r.currency, displayCurrency, rate)
          const dispSym = displayP != null ? CURRENCY_SYMBOL[displayCurrency] : CURRENCY_SYMBOL[r.currency]
          const dispVal = displayP != null ? displayP : p
          return (
            <span style={{ color: up ? upColor : downColor }}>
              {up ? '+' : ''}{dispSym || ''}{fmt(dispVal)}
              <span style={{ fontSize: 12, marginLeft: 4 }}>({up ? '+' : ''}{pct.toFixed(1)}%)</span>
            </span>
          )
        },
      },
      {
        title: '仓位比例',
        width: 180,
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
      title: '账户/平台',
      dataIndex: 'name',
      render: (text, r) => (
        <Space direction="vertical" size={0}>
          <Link to={`/platforms/${r.id}`}>{text}</Link>
          <span style={{ color: '#999', fontSize: 12 }}>{r.note || '无备注'}</span>
        </Space>
      ),
    },
    {
      title: `资产规模（${sym}）`,
      align: 'right',
      width: 180,
      sorter: (a, b) => platformTotal(a.id) - platformTotal(b.id),
      render: (_, r) => <strong>{sym}{fmt(platformTotal(r.id))}</strong>,
    },
    {
      title: '持仓数',
      align: 'right',
      width: 100,
      render: (_, r) => (byPlatform[r.id] || []).length,
    },
    {
      title: '操作',
      width: 240,
      render: (_, r) => (
        <Space>
          <Link to={`/platforms/${r.id}`}>查看明细</Link>
          <a onClick={() => openEdit(r)}>编辑</a>
          <Popconfirm title="删除该账户及其下所有资产？" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <Card>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} md={14}>
            <div style={{ color: '#8c8c8c', marginBottom: 6 }}>资产账户</div>
            <div style={{ fontSize: 30, fontWeight: 800 }}>{sym}{fmt(grandTotal)}</div>
            <div style={{ marginTop: 6, color: '#8c8c8c' }}>
              {data.length} 个账户 · {holdings.length} 条持仓 · USD/CNY {rate ?? '未刷新'}
            </div>
          </Col>
          <Col xs={24} md={10} style={{ textAlign: 'right' }}>
            <Space wrap style={{ justifyContent: 'flex-end' }}>
              <Segmented
                value={displayCurrency}
                onChange={setDisplayCurrency}
                options={[
                  { label: '¥ 人民币', value: 'CNY' },
                  { label: '$ 美元', value: 'USD' },
                ]}
              />
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
                添加账户
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {accountCards.length ? (
        <Row gutter={[16, 16]}>
          {accountCards.map((p) => (
            <Col xs={24} md={12} xl={8} key={p.id}>
              <Card
                size="small"
                title={<Link to={`/platforms/${p.id}`}>{p.name}</Link>}
                extra={<Link to={`/platforms/${p.id}`}><ArrowRightOutlined /></Link>}
                style={{ height: '100%' }}
              >
                <div style={{ fontSize: 24, fontWeight: 700 }}>{sym}{fmt(p.total)}</div>
                <Progress percent={Number(p.pct.toFixed(1))} size="small" style={{ marginTop: 12 }} />
                <Space size={8} wrap style={{ marginTop: 10 }}>
                  <Tag>{p.holdingCount} 条持仓</Tag>
                  {p.topHolding && <Tag color="blue">最大：{p.topHolding.name || p.topHolding.symbol}</Tag>}
                </Space>
                {p.note && <div style={{ color: '#8c8c8c', marginTop: 10 }}>{p.note}</div>}
              </Card>
            </Col>
          ))}
        </Row>
      ) : (
        <Card>
          <Empty
            description="还没有账户。先添加一个券商、银行或钱包账户，再录入资产。"
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加账户</Button>
          </Empty>
        </Card>
      )}

      <Card title="账户明细" loading={loading}>
        <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          pagination={false}
          expandable={{
            expandedRowRender,
            rowExpandable: (r) => (byPlatform[r.id] || []).length > 0,
          }}
        />
      </Card>

      <Modal title={editing ? '编辑账户' : '添加账户'} open={open} onOk={submit} onCancel={() => setOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="账户名称" rules={[{ required: true, message: '请输入账户名称' }]}>
            <Input placeholder="如：富途、盈透 IBKR、老虎证券、招商银行、加密钱包" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="可选，例如账户用途、地区、币种或风险提示" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
