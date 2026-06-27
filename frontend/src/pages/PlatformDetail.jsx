import { useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Button, Card, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Segmented, Select, Space, Switch, Table, Tag, Tooltip, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined, ArrowLeftOutlined, LinkOutlined, WarningOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listPlatforms, listHoldings, createHolding, updateHolding, deleteHolding, refreshPrices, createTransaction,
} from '../api'
import {
  CURRENCIES, ASSET_TYPES, MARKETS, MARKET_LABEL, ASSET_TYPE_LABEL, CURRENCY_SYMBOL, fmt,
} from '../constants'
import { marketValue, dayChange, costBasis, profitOf, isDerived, isClosed, isAnomalous } from '../holdings'
import { useColorScheme } from '../colorScheme.jsx'

export default function PlatformDetail() {
  const { upColor, downColor } = useColorScheme()
  const { id } = useParams()
  const platformId = Number(id)
  const [platform, setPlatform] = useState(null)
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showClosed, setShowClosed] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [mode, setMode] = useState('derived')
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [plats, holdings] = await Promise.all([
        listPlatforms(),
        listHoldings({ platform_id: platformId, include_closed: showClosed }),
      ])
      setPlatform(plats.find((p) => p.id === platformId) || null)
      setData(holdings)
    } catch (e) {
      message.error('加载失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [platformId, showClosed]) // eslint-disable-line react-hooks/exhaustive-deps

  const doRefresh = async () => {
    setRefreshing(true)
    try {
      const res = await refreshPrices()
      message.success(`已更新 ${res.updated}/${res.total} 条行情`)
      load()
    } catch (e) {
      message.error('更新行情失败：' + e.message)
    } finally {
      setRefreshing(false)
    }
  }

  const openAdd = () => {
    setEditing(null)
    setMode('derived')
    form.resetFields()
    form.setFieldsValue({ currency: 'CNY', asset_type: 'stock', market: 'A', date: dayjs() })
    setOpen(true)
  }
  const openEdit = (r) => {
    setEditing(r)
    setMode(r.source === 'derived' ? 'derived' : 'manual')
    form.setFieldsValue(r)
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        // 编辑：derived 持仓只改可改字段；数量/成本由流水决定
        const patch = editing.source === 'derived'
          ? { name: values.name, asset_type: values.asset_type, market: values.market }
          : values
        await updateHolding(editing.id, patch)
      } else if (mode === 'derived') {
        // 按交易记录：记一笔买入，后端自动建/更新 derived 持仓
        await createTransaction({
          platform_id: platformId, action: 'buy',
          date: values.date ? values.date.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD'),
          name: values.name, symbol: values.symbol, currency: values.currency,
          quantity: values.quantity, price: values.price, fee: values.fee,
        })
      } else {
        await createHolding({ ...values, platform_id: platformId, source: 'manual' })
      }
      message.success('已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const remove = async (hid) => {
    try {
      await deleteHolding(hid)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  const columns = useMemo(() => [
    {
      title: '名称', dataIndex: 'name',
      render: (t, r) => (
        <Space direction="vertical" size={0}>
          <Space size={4}>
            <span>{t || '（未命名）'}</span>
            {isDerived(r) && (
              <Tooltip title="由交易流水计算：数量/成本只读，请到「交易记录」增删流水">
                <Tag color="blue" icon={<LinkOutlined />} style={{ marginInlineStart: 0 }}>流水</Tag>
              </Tooltip>
            )}
            {isClosed(r) && <Tag>已清仓</Tag>}
            {isAnomalous(r) && (
              <Tooltip title="持仓数量为负，可能漏录了买入，请检查交易流水">
                <Tag color="warning" icon={<WarningOutlined />}>数量异常</Tag>
              </Tooltip>
            )}
          </Space>
          <span style={{ color: '#999', fontSize: 12 }}>{r.symbol}</span>
        </Space>
      ),
    },
    { title: '类型', dataIndex: 'asset_type', render: (v) => ASSET_TYPE_LABEL[v] },
    { title: '市场', dataIndex: 'market', render: (v) => MARKET_LABEL[v] },
    { title: '币种', dataIndex: 'currency', render: (v) => <Tag>{v}</Tag> },
    { title: '数量', dataIndex: 'quantity', align: 'right', render: (v) => (v == null ? '—' : v) },
    {
      title: '现价', dataIndex: 'current_price', align: 'right',
      render: (v, r) => (v == null ? '—' : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(v)}`),
    },
    {
      title: '市值', align: 'right',
      render: (_, r) => `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(marketValue(r))}`,
      sorter: (a, b) => marketValue(a) - marketValue(b),
    },
    {
      title: '今日涨跌', align: 'right',
      render: (_, r) => {
        const c = dayChange(r)
        if (!c) return '—'
        const up = c >= 0
        return <span style={{ color: up ? upColor : downColor }}>{up ? '+' : ''}{fmt(c)}</span>
      },
    },
    {
      title: '成本', align: 'right',
      render: (_, r) => {
        const cb = costBasis(r)
        return cb == null ? '—' : `${CURRENCY_SYMBOL[r.currency] || ''}${fmt(cb)}`
      },
    },
    {
      title: '盈亏', align: 'right',
      sorter: (a, b) => (profitOf(a) ?? -Infinity) - (profitOf(b) ?? -Infinity),
      render: (_, r) => {
        const p = profitOf(r)
        if (p == null) return '—'
        const cb = costBasis(r)
        const pct = cb ? (p / cb) * 100 : 0
        const up = p >= 0
        return (
          <span style={{ color: up ? upColor : downColor }}>
            {up ? '+' : ''}{CURRENCY_SYMBOL[r.currency] || ''}{fmt(p)}
            <span style={{ fontSize: 12, marginLeft: 4 }}>({up ? '+' : ''}{pct.toFixed(1)}%)</span>
          </span>
        )
      },
    },
    {
      title: '已实现', align: 'right',
      render: (_, r) => {
        const realized = (r.realized_pnl || 0) + (r.realized_income || 0)
        if (!isDerived(r) || realized === 0) return '—'
        const up = realized >= 0
        return (
          <Tooltip title={`已实现盈亏 ${fmt(r.realized_pnl || 0)} + 分红 ${fmt(r.realized_income || 0)}`}>
            <span style={{ color: up ? upColor : downColor }}>
              {up ? '+' : ''}{CURRENCY_SYMBOL[r.currency] || ''}{fmt(realized)}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '操作', width: 130,
      render: (_, r) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          {isDerived(r) ? (
            <Tooltip title="该持仓由交易流水驱动，请在「交易记录」删除其流水">
              <span style={{ color: '#ccc', cursor: 'not-allowed' }}>删除</span>
            </Tooltip>
          ) : (
            <Popconfirm title="删除该资产？" onConfirm={() => remove(r.id)}>
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ], [])

  return (
    <Card
      title={
        <Space>
          <Link to="/platforms"><ArrowLeftOutlined /></Link>
          {platform ? platform.name : '平台'} · 资产管理
        </Space>
      }
      extra={
        <Space>
          <Space size={4}>
            <span style={{ color: '#888', fontSize: 13 }}>显示已清仓</span>
            <Switch size="small" checked={showClosed} onChange={setShowClosed} />
          </Space>
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={doRefresh}>更新行情</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加资产</Button>
        </Space>
      }
    >
      <Table rowKey="id" loading={loading} dataSource={data} columns={columns} pagination={false} scroll={{ x: 860 }}
        rowClassName={(r) => (isClosed(r) ? 'row-closed' : '')} />

      <Modal
        title={editing ? '编辑资产' : '添加资产'}
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {!editing && (
            <Segmented
              block
              value={mode}
              onChange={setMode}
              style={{ marginBottom: 16 }}
              options={[
                { label: '按交易记录（推荐）', value: 'derived' },
                { label: '直接手填', value: 'manual' },
              ]}
            />
          )}
          <Space style={{ display: 'flex' }}>
            <Form.Item name="currency" label="币种" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={CURRENCIES} />
            </Form.Item>
            <Form.Item name="asset_type" label="类型" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={ASSET_TYPES} />
            </Form.Item>
            <Form.Item name="market" label="市场（决定行情源）" rules={[{ required: true }]} style={{ flex: 1.4 }}>
              <Select options={MARKETS} />
            </Form.Item>
          </Space>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：Apple、贵州茅台、腾讯控股" />
          </Form.Item>
          <Form.Item name="symbol" label="代码" extra="A股如 600519，美股如 AAPL，港股如 00700，基金填基金代码；现金可留空">
            <Input placeholder="行情代码" />
          </Form.Item>
          {(mode === 'derived' && !editing) ? (
            <Space style={{ display: 'flex' }}>
              <Form.Item name="date" label="买入日期" rules={[{ required: true }]} style={{ flex: 1 }}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="quantity" label="买入数量" rules={[{ required: true }]} style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="股数/份额" />
              </Form.Item>
              <Form.Item name="price" label="买入价" rules={[{ required: true }]} style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="成交价" />
              </Form.Item>
              <Form.Item name="fee" label="费用" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="手续费" />
              </Form.Item>
            </Space>
          ) : (
            <Space style={{ display: 'flex' }}>
              <Form.Item name="quantity" label="持有数量/份额" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="股数/份额" disabled={editing?.source === 'derived'} />
              </Form.Item>
              <Form.Item name="cost_price" label="成本价（可选）" style={{ flex: 1 }}>
                <InputNumber style={{ width: '100%' }} placeholder="用于盈亏" disabled={editing?.source === 'derived'} />
              </Form.Item>
              <Form.Item name="manual_value" label="手填市值（无法抓价时）" style={{ flex: 1.2 }}>
                <InputNumber style={{ width: '100%' }} placeholder="现金/债券等直接填金额" disabled={editing?.source === 'derived'} />
              </Form.Item>
            </Space>
          )}
          {editing?.source === 'derived' && (
            <div style={{ color: '#888', fontSize: 12, marginTop: -8 }}>
              数量与成本由交易流水自动计算，如需调整请到「交易记录」增删对应流水。
            </div>
          )}
        </Form>
      </Modal>
    </Card>
  )
}
