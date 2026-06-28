import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, DatePicker, Drawer, Empty, Form, Input, InputNumber, Modal, Popconfirm, Row,
  Segmented, Select, Space, Spin, Switch, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import { BookOutlined, PlusOutlined, ReloadOutlined, ArrowLeftOutlined, LinkOutlined, WarningOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listPlatforms, listHoldings, createHolding, updateHolding, deleteHolding, refreshPrices,
  createTransaction, getRate, getHoldingResearchBrief,
} from '../api'
import {
  CURRENCIES, ASSET_TYPES, MARKETS, MARKET_LABEL, ASSET_TYPE_LABEL, CURRENCY_SYMBOL, fmt,
} from '../constants'
import { marketValue, dayChange, costBasis, profitOf, isDerived, isClosed, isAnomalous } from '../holdings'
import { useColorScheme } from '../colorScheme.jsx'
import { useDisplaySettings, convertAmount } from '../displaySettings.jsx'

const NOTE_TYPE_LABEL = {
  thesis: '买入逻辑', risk: '风险点', review: '复盘',
  action: '行动项', observation: '观察', general: '笔记',
}
const NOTE_TYPE_COLOR = {
  thesis: 'blue', risk: 'red', review: 'purple',
  action: 'orange', observation: 'cyan', general: 'default',
}

export default function PlatformDetail() {
  const navigate = useNavigate()
  const { upColor, downColor } = useColorScheme()
  const { displayCurrency } = useDisplaySettings()
  const { id } = useParams()
  const platformId = Number(id)
  const [platform, setPlatform] = useState(null)
  const [data, setData] = useState([])
  const [fx, setFx] = useState(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showClosed, setShowClosed] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [mode, setMode] = useState('derived')
  const [form] = Form.useForm()

  // Research brief drawer
  const [briefOpen, setBriefOpen] = useState(false)
  const [briefHolding, setBriefHolding] = useState(null)
  const [briefData, setBriefData] = useState(null)
  const [briefLoading, setBriefLoading] = useState(false)

  const rate = fx?.updated_at ? fx.rate : null
  const conv = (amount, srcCur) => {
    const result = convertAmount(amount, srcCur, displayCurrency, rate)
    return result != null
      ? { value: result, sym: CURRENCY_SYMBOL[displayCurrency] || '' }
      : { value: amount, sym: CURRENCY_SYMBOL[srcCur] || '' }
  }

  const load = async () => {
    setLoading(true)
    try {
      const [plats, holdings, fxRate] = await Promise.all([
        listPlatforms(),
        listHoldings({ platform_id: platformId, include_closed: showClosed }),
        getRate(),
      ])
      setPlatform(plats.find((p) => p.id === platformId) || null)
      setData(holdings)
      setFx(fxRate)
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

  const openResearchBrief = async (holding) => {
    setBriefHolding(holding)
    setBriefData(null)
    setBriefOpen(true)
    setBriefLoading(true)
    try {
      setBriefData(await getHoldingResearchBrief(holding.id))
    } catch (e) {
      message.error('加载研究记录失败：' + e.message)
    } finally {
      setBriefLoading(false)
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
      render: (_, r) => {
        const { value, sym } = conv(marketValue(r), r.currency)
        return `${sym}${fmt(value)}`
      },
      sorter: (a, b) => marketValue(a) - marketValue(b),
    },
    {
      title: '今日涨跌', align: 'right',
      render: (_, r) => {
        const c = dayChange(r)
        if (!c) return '—'
        const up = c >= 0
        const { value, sym } = conv(c, r.currency)
        return <span style={{ color: up ? upColor : downColor }}>{up ? '+' : ''}{sym}{fmt(value)}</span>
      },
    },
    {
      title: '成本', align: 'right',
      render: (_, r) => {
        const cb = costBasis(r)
        if (cb == null) return '—'
        const { value, sym } = conv(cb, r.currency)
        return `${sym}${fmt(value)}`
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
        const { value, sym } = conv(p, r.currency)
        return (
          <span style={{ color: up ? upColor : downColor }}>
            {up ? '+' : ''}{sym}{fmt(value)}
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
        const { value, sym } = conv(realized, r.currency)
        const { value: pnlVal } = conv(r.realized_pnl || 0, r.currency)
        const { value: incVal } = conv(r.realized_income || 0, r.currency)
        return (
          <Tooltip title={`已实现盈亏 ${fmt(pnlVal)} + 分红 ${fmt(incVal)}`}>
            <span style={{ color: up ? upColor : downColor }}>
              {up ? '+' : ''}{sym}{fmt(value)}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '操作', width: 180,
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
          <Tooltip title="查看相关研究记录和报告">
            <a onClick={() => openResearchBrief(r)} style={{ color: '#1677ff' }}>
              <BookOutlined />
            </a>
          </Tooltip>
        </Space>
      ),
    },
  ], [upColor, downColor, displayCurrency, rate]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card
      title={
        <Space>
          <Link to="/platforms"><ArrowLeftOutlined /></Link>
          {platform ? platform.name : '平台'} · 资产管理
        </Space>
      }
      extra={
        <Space wrap size={[8, 6]}>
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

      {/* Research Brief Drawer */}
      <Drawer
        title={
          <Space>
            <BookOutlined />
            <span>研究记录</span>
            {briefHolding && (
              <Tag>{briefHolding.name}{briefHolding.symbol ? ` (${briefHolding.symbol})` : ''}</Tag>
            )}
          </Space>
        }
        open={briefOpen}
        onClose={() => setBriefOpen(false)}
        width={420}
        footer={
          briefHolding?.symbol ? (
            <Space>
              <Button size="small" onClick={() => navigate(`/notes?symbol=${briefHolding.symbol}`)}>
                查看全部相关笔记
              </Button>
              <Button size="small" onClick={() => navigate('/research')}>
                去投研工作台
              </Button>
            </Space>
          ) : (
            <Button size="small" onClick={() => navigate('/research')}>去投研工作台</Button>
          )
        }
      >
        {briefLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : briefData ? (
          <div>
            {/* Notes grouped by type priority */}
            {['thesis', 'action', 'risk', 'review', 'observation', 'general'].map((nt) => {
              const group = briefData.notes.filter((n) => n.note_type === nt)
              if (!group.length) return null
              const label = NOTE_TYPE_LABEL[nt] || nt
              const color = NOTE_TYPE_COLOR[nt] || 'default'
              return (
                <div key={nt} style={{ marginBottom: 16 }}>
                  <Tag color={color} style={{ marginBottom: 8 }}>{label}</Tag>
                  {group.map((n) => (
                    <div key={n.id} style={{ background: '#fafafa', borderRadius: 6, padding: '8px 10px', marginBottom: 6, fontSize: 13 }}>
                      {n.title && <div style={{ fontWeight: 500, marginBottom: 4 }}>{n.title}</div>}
                      <div style={{ color: '#595959', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                        {n.content.length > 150 ? n.content.slice(0, 150) + '…' : n.content}
                      </div>
                      <div style={{ marginTop: 4, color: '#bbb', fontSize: 11 }}>
                        {n.status !== 'active' && <Tag style={{ fontSize: 10 }}>{n.status}</Tag>}
                        {n.updated_at?.slice(0, 10)}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}

            {/* Reports */}
            {briefData.reports.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Tag color="geekblue" style={{ marginBottom: 8 }}>AI 报告</Tag>
                {briefData.reports.map((r) => (
                  <div key={r.id} style={{ background: '#f0f5ff', borderRadius: 6, padding: '8px 10px', marginBottom: 6 }}>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{r.title || r.target_name}</div>
                    <Space size={4} style={{ marginTop: 4, flexWrap: 'wrap' }}>
                      <Tag style={{ fontSize: 10 }}>{r.status === 'completed' ? '已完成' : r.status}</Tag>
                      <Tag style={{ fontSize: 10 }}>{r.report_language === 'en' ? 'EN' : '中文'}</Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{r.updated_at?.slice(0, 10)}</Typography.Text>
                    </Space>
                  </div>
                ))}
              </div>
            )}

            {briefData.notes.length === 0 && briefData.reports.length === 0 && (
              <Empty description="暂无相关研究记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>
        ) : null}
      </Drawer>

      <Modal
        title={editing ? '编辑资产' : '添加资产'}
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {!editing && (
            <>
              <Segmented
                block
                value={mode}
                onChange={setMode}
                style={{ marginBottom: 8 }}
                options={[
                  { label: '通过交易自动计算（推荐）', value: 'derived' },
                  { label: '手动维护市值', value: 'manual' },
                ]}
              />
              <div style={{ marginBottom: 16, fontSize: 12, color: '#8c8c8c' }}>
                {mode === 'derived'
                  ? '适合股票、基金、ETF 等——先记买入交易，系统自动计算持仓数量和成本。'
                  : '适合现金、债券、私募、无法自动抓价的资产——直接填入当前市值即可。'}
              </div>
            </>
          )}
          <Row gutter={8}>
            <Col xs={24} md={8}>
              <Form.Item name="currency" label="币种" rules={[{ required: true }]}>
                <Select options={CURRENCIES} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="asset_type" label="类型" rules={[{ required: true }]}>
                <Select options={ASSET_TYPES} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="market" label="市场（决定行情源）" rules={[{ required: true }]}>
                <Select options={MARKETS} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：Apple、贵州茅台、腾讯控股" />
          </Form.Item>
          <Form.Item name="symbol" label="代码" extra="A股如 600519，美股如 AAPL，港股如 00700，基金填基金代码；现金可留空">
            <Input placeholder="行情代码" />
          </Form.Item>
          {(mode === 'derived' && !editing) ? (
            <Row gutter={8}>
              <Col xs={24} md={6}>
                <Form.Item name="date" label="买入日期" rules={[{ required: true }]}>
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="quantity" label="买入数量" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="股数/份额" />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="price" label="买入价" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="成交价" />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="fee" label="费用">
                  <InputNumber style={{ width: '100%' }} placeholder="手续费" />
                </Form.Item>
              </Col>
            </Row>
          ) : (
            <Row gutter={8}>
              <Col xs={24} md={8}>
                <Form.Item name="quantity" label="持有数量/份额">
                  <InputNumber style={{ width: '100%' }} placeholder="股数/份额" disabled={editing?.source === 'derived'} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item name="cost_price" label="成本价（可选）">
                  <InputNumber style={{ width: '100%' }} placeholder="用于盈亏" disabled={editing?.source === 'derived'} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item name="manual_value" label="手填市值">
                  <InputNumber style={{ width: '100%' }} placeholder="现金/债券等" disabled={editing?.source === 'derived'} />
                </Form.Item>
              </Col>
            </Row>
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
