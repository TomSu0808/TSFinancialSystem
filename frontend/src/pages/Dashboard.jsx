import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Empty, Row, Segmented, Space, Steps, Tag, Tooltip, message,
} from 'antd'
import {
  ReloadOutlined, ArrowUpOutlined, ArrowDownOutlined,
  EditOutlined, InfoCircleOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, RightOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { getSummary, getSnapshots, refreshPrices, refreshRate } from '../api'
import { CURRENCY_SYMBOL, CURRENCY_LABEL, ASSET_TYPE_LABEL, fmt, isMasked } from '../constants'
import { useColorScheme } from '../colorScheme.jsx'
import { useDisplaySettings } from '../displaySettings.jsx'

function MetricCard({ label, value, sub, tone }) {
  return (
    <Card size="small" style={{ height: '100%' }}>
      <div style={{ color: '#8c8c8c', fontSize: 13 }}>{label}</div>
      <div style={{ marginTop: 8, fontSize: 22, fontWeight: 700, color: tone || 'inherit' }}>
        {value}
      </div>
      {sub && <div style={{ marginTop: 6, color: '#8c8c8c', fontSize: 12 }}>{sub}</div>}
    </Card>
  )
}

export default function Dashboard({ autoRefresh = false }) {
  const { upColor: RED, downColor: GREEN } = useColorScheme()
  const { displayCurrency, setDisplayCurrency } = useDisplaySettings()
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, snaps] = await Promise.all([getSummary(displayCurrency), getSnapshots(180)])
      setSummary(s)
      setSnapshots(snaps)
    } catch (e) {
      message.error('加载汇总失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }, [displayCurrency])

  useEffect(() => {
    load()
  }, [load])

  const doRefresh = async () => {
    setRefreshing(true)
    try {
      const [prices, fx] = await Promise.allSettled([refreshPrices(), refreshRate()])
      if (prices.status === 'fulfilled') {
        message.success(`已更新 ${prices.value.updated}/${prices.value.total} 条行情`)
      } else {
        message.warning('部分行情更新失败，请检查网络或代码')
      }
      if (fx.status === 'rejected') {
        message.warning('汇率刷新失败，暂用最近一次缓存')
      }
      await load()
    } finally {
      setRefreshing(false)
    }
  }

  const didAuto = useRef(false)
  useEffect(() => {
    if (autoRefresh && !didAuto.current) {
      didAuto.current = true
      doRefresh()
    }
  }, [autoRefresh]) // eslint-disable-line react-hooks/exhaustive-deps

  const masked = isMasked()
  const sym = CURRENCY_SYMBOL[displayCurrency]
  const change = summary?.change ?? 0
  const up = change >= 0
  const changeColor = up ? RED : GREEN

  const totalProfit = summary?.total_profit ?? 0
  const realizedPnl = summary?.realized_pnl ?? 0
  const realizedIncome = summary?.realized_income ?? 0
  const totalReturn = summary?.total_return ?? totalProfit
  const returnUp = totalReturn >= 0
  const returnColor = returnUp ? RED : GREEN
  const total = summary?.total ?? 0

  const byCur = (code) => summary?.by_currency?.find((c) => c.currency === code)
  const byType = (code) => summary?.by_type?.find((x) => x.asset_type === code)
  const pct = (value) => (total ? `${((value || 0) / total * 100).toFixed(1)}%` : '0.0%')
  const cashTotal = byType('cash')?.display_total ?? 0
  const stockTotal = (byType('stock')?.display_total ?? 0) + (byType('etf')?.display_total ?? 0)
  const largestPlatform = summary?.by_platform?.[0]

  const isNewUser = !loading && summary !== null && total === 0

  const insights = []
  if (summary && total > 0) {
    if (largestPlatform) {
      const lpPct = largestPlatform.display_total / total * 100
      insights.push({
        warning: lpPct >= 50,
        text: `最大平台「${largestPlatform.platform}」占总资产 ${lpPct.toFixed(0)}%${lpPct >= 50 ? '，集中度偏高，建议分散配置' : ''}`,
      })
    }
    const cashPct = total ? cashTotal / total * 100 : 0
    insights.push({ warning: false, text: `现金类资产占比 ${cashPct.toFixed(0)}%` })
    const stockPct = total ? stockTotal / total * 100 : 0
    if (stockPct > 0) {
      insights.push({ warning: false, text: `股票 / ETF 占比 ${stockPct.toFixed(0)}%` })
    }
    if ((summary.total_cost ?? 0) === 0) {
      insights.push({ warning: true, text: '尚未录入成本信息，收益率数据暂无法统计' })
    }
    if (!summary.rate) {
      insights.push({ warning: true, text: '汇率未刷新，多币种换算可能不准确，建议点击更新' })
    }
  }

  const pie = (data, nameKey, mapName) => ({
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}: ${masked ? '****' : sym + fmt(p.value)} (${p.percent}%)`,
    },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie',
      radius: ['48%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%' },
      data: (data || []).map((x) => ({
        name: mapName ? mapName(x[nameKey]) : x[nameKey],
        value: x.display_total,
      })),
    }],
  })

  const trendOption = {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${sym}${fmt(v)}` },
    grid: { left: 60, right: 24, top: 24, bottom: 36 },
    xAxis: { type: 'category', data: snapshots.map((s) => s.day) },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v) => (masked ? '***' : `${sym}${(v / 10000).toFixed(1)}w`) },
    },
    series: [{
      type: 'line',
      smooth: true,
      showSymbol: snapshots.length < 30,
      areaStyle: { opacity: 0.12 },
      lineStyle: { width: 2 },
      data: snapshots.map((s) => (displayCurrency === 'CNY' ? s.total_cny : s.total_usd)),
    }],
  }

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <Card loading={loading} bodyStyle={{ padding: 24 }}>
        <Row gutter={[24, 24]} align="middle">
          <Col xs={24} md={15}>
            <div style={{ color: '#8c8c8c', marginBottom: 8 }}>总资产（{CURRENCY_LABEL[displayCurrency]}）</div>
            <div style={{ fontSize: 44, fontWeight: 800, lineHeight: 1.05 }}>
              {sym}{fmt(total)}
            </div>
            <Space size={18} wrap style={{ marginTop: 16 }}>
              <Space size={6}>
                <span style={{ color: changeColor, fontSize: 16 }}>
                  {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {sym}{fmt(Math.abs(change))}
                </span>
                <span style={{ color: changeColor }}>({up ? '+' : ''}{summary?.change_pct ?? 0}%)</span>
                <span style={{ color: '#8c8c8c' }}>今日</span>
              </Space>
              <Tooltip
                title={(
                  <div>
                    <div>未实现盈亏：{sym}{fmt(totalProfit)}</div>
                    <div>已实现盈亏：{sym}{fmt(realizedPnl)}</div>
                    <div>分红/利息：{sym}{fmt(realizedIncome)}</div>
                  </div>
                )}
              >
                <Space size={6}>
                  <span style={{ color: returnColor, fontSize: 16 }}>
                    {returnUp ? '+' : ''}{sym}{fmt(totalReturn)}
                  </span>
                  <span style={{ color: '#8c8c8c' }}>总收益</span>
                </Space>
              </Tooltip>
            </Space>
          </Col>
          <Col xs={24} md={9} style={{ textAlign: 'right' }}>
            <Space direction="vertical" align="end" size={12}>
              <Segmented
                value={displayCurrency}
                onChange={setDisplayCurrency}
                options={[{ label: '¥ 人民币', value: 'CNY' }, { label: '$ 美元', value: 'USD' }]}
              />
              <Space size={8} wrap style={{ justifyContent: 'flex-end' }}>
                <Button
                  icon={<EditOutlined />}
                  onClick={() => navigate('/transactions', { state: { openAdd: true } })}
                >
                  记一笔
                </Button>
                <Button type="primary" icon={<ReloadOutlined />} loading={refreshing} onClick={doRefresh}>
                  更新行情与汇率
                </Button>
              </Space>
              <Tag>USD/CNY {summary?.rate ?? '未刷新'}</Tag>
            </Space>
          </Col>
        </Row>
      </Card>

      {isNewUser && (
        <Card title="开始使用" style={{ borderColor: '#1677ff22' }}>
          <div style={{ marginBottom: 16, color: '#595959', fontSize: 14 }}>
            欢迎！按以下步骤开始记录你的资产状况：
          </div>
          <Steps
            direction="vertical"
            size="small"
            current={0}
            style={{ maxWidth: 520 }}
            items={[
              {
                title: '创建第一个账户',
                description: (
                  <span>
                    在「资产账户」页添加一个券商、银行或钱包账户。
                    {' '}
                    <Link to="/platforms" style={{ fontWeight: 500 }}>
                      去添加 <RightOutlined style={{ fontSize: 11 }} />
                    </Link>
                  </span>
                ),
                status: 'process',
              },
              {
                title: '记录第一笔交易或添加持仓',
                description: (
                  <span>
                    有了账户后，记录一笔买入来建立你的第一个持仓；也可以直接手填现有资产。
                    {' '}
                    <a
                      style={{ fontWeight: 500 }}
                      onClick={() => navigate('/transactions', { state: { openAdd: true } })}
                    >
                      记一笔 <RightOutlined style={{ fontSize: 11 }} />
                    </a>
                  </span>
                ),
                status: 'wait',
              },
              {
                title: '回到这里查看总览',
                description: '记录后，这里会显示你的资产分布、收益走势和今日涨跌。',
                status: 'wait',
              },
            ]}
          />
          <div style={{ marginTop: 16, color: '#8c8c8c', fontSize: 12 }}>
            还可以在「个人资料」中设置 AI Key、导出备份，保护你的数据安全。
          </div>
        </Card>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <MetricCard label="现金占比" value={pct(cashTotal)} sub={`${sym}${fmt(cashTotal)}`} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard label="股票/ETF占比" value={pct(stockTotal)} sub={`${sym}${fmt(stockTotal)}`} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard
            label="最大平台"
            value={largestPlatform?.platform || '暂无'}
            sub={largestPlatform ? `${sym}${fmt(largestPlatform.display_total)} · ${pct(largestPlatform.display_total)}` : '添加账户后显示'}
          />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard
            label="累计收益率"
            value={`${summary?.profit_pct ?? 0}%`}
            sub={`成本 ${sym}${fmt(summary?.total_cost ?? 0)}`}
            tone={(summary?.profit_pct ?? 0) >= 0 ? RED : GREEN}
          />
        </Col>
      </Row>

      {insights.length > 0 && (
        <Card
          size="small"
          title={<Space size={6}><InfoCircleOutlined style={{ color: '#1677ff' }} />值得关注</Space>}
        >
          <Space direction="vertical" style={{ display: 'flex' }} size={8}>
            {insights.map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13 }}>
                {item.warning
                  ? <ExclamationCircleOutlined style={{ color: '#faad14', marginTop: 2, flexShrink: 0 }} />
                  : <CheckCircleOutlined style={{ color: '#52c41a', marginTop: 2, flexShrink: 0 }} />}
                <span style={{ color: item.warning ? '#595959' : '#595959' }}>{item.text}</span>
              </div>
            ))}
          </Space>
        </Card>
      )}

      <Card loading={loading} title="总资产走势">
        {snapshots.length > 1 ? (
          <ReactECharts option={trendOption} style={{ height: 320 }} notMerge />
        ) : (
          <Empty description="走势需要至少 2 天数据；每天打开总览会自动记录一个净值点" />
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <MetricCard
            label="人民币资产"
            value={`¥${fmt(byCur('CNY')?.native_total ?? 0)}`}
            sub={`折合 ${sym}${fmt(byCur('CNY')?.display_total ?? 0)}`}
          />
        </Col>
        <Col xs={24} md={8}>
          <MetricCard
            label="美元资产"
            value={`$${fmt(byCur('USD')?.native_total ?? 0)}`}
            sub={`折合 ${sym}${fmt(byCur('USD')?.display_total ?? 0)}`}
          />
        </Col>
        <Col xs={24} md={8}>
          <MetricCard
            label="港币资产"
            value={`HK$${fmt(byCur('HKD')?.native_total ?? 0)}`}
            sub={`折合 ${sym}${fmt(byCur('HKD')?.display_total ?? 0)}`}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card loading={loading} title="平台占比">
            {summary?.by_platform?.length ? (
              <ReactECharts option={pie(summary.by_platform, 'platform')} style={{ height: 300 }} notMerge />
            ) : (
              <Empty description={<span>还没有资产，去 <Link to="/platforms">资产账户</Link> 添加</span>} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card loading={loading} title="资产类型占比">
            {summary?.by_type?.length ? (
              <ReactECharts option={pie(summary.by_type, 'asset_type', (t) => ASSET_TYPE_LABEL[t] || t)} style={{ height: 300 }} notMerge />
            ) : (
              <Empty description="添加资产后显示类型占比" />
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
