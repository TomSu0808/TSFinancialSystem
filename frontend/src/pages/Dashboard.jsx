import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Button, Card, Col, Empty, Row, Segmented, Space, Tag, Tooltip, message,
} from 'antd'
import { ReloadOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { getSummary, getSnapshots, refreshPrices, refreshRate } from '../api'
import { CURRENCY_SYMBOL, CURRENCY_LABEL, ASSET_TYPE_LABEL, fmt, isMasked } from '../constants'

const RED = '#cf1322'   // 国内习惯：红涨/红盈
const GREEN = '#3f8600' // 绿跌/绿亏

export default function Dashboard({ autoRefresh = false }) {
  const [currency, setCurrency] = useState('CNY')
  const [summary, setSummary] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (cur) => {
    setLoading(true)
    try {
      const [s, snaps] = await Promise.all([getSummary(cur), getSnapshots(180)])
      setSummary(s)
      setSnapshots(snaps)
    } catch (e) {
      message.error('加载汇总失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(currency)
  }, [currency, load])

  // 「更新行情」：先拉行情 + 汇率，再刷新汇总
  const doRefresh = async () => {
    setRefreshing(true)
    try {
      const [prices] = await Promise.allSettled([refreshPrices(), refreshRate()])
      if (prices.status === 'fulfilled') {
        message.success(`已更新 ${prices.value.updated}/${prices.value.total} 条行情`)
      } else {
        message.warning('部分行情更新失败，请检查网络/代码')
      }
      await load(currency)
    } finally {
      setRefreshing(false)
    }
  }

  // 开启「进总览自动刷新」时，进入页面自动更新一次行情
  const didAuto = useRef(false)
  useEffect(() => {
    if (autoRefresh && !didAuto.current) {
      didAuto.current = true
      doRefresh()
    }
  }, [autoRefresh]) // eslint-disable-line react-hooks/exhaustive-deps

  const masked = isMasked()
  const sym = CURRENCY_SYMBOL[currency]
  const change = summary?.change ?? 0
  const up = change >= 0
  const changeColor = up ? RED : GREEN

  const totalProfit = summary?.total_profit ?? 0
  const profitUp = totalProfit >= 0
  const profitColor = profitUp ? RED : GREEN

  const pie = (data, nameKey, mapName) => ({
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}: ${masked ? '****' : sym + fmt(p.value)} (${p.percent}%)`,
    },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%' },
      data: (data || []).map((x) => ({ name: mapName ? mapName(x[nameKey]) : x[nameKey], value: x.display_total })),
    }],
  })

  const trendOption = {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${sym}${fmt(v)}` },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: snapshots.map((s) => s.day) },
    yAxis: { type: 'value', scale: true, axisLabel: { formatter: (v) => (masked ? '***' : `${sym}${(v / 10000).toFixed(1)}w`) } },
    series: [{
      type: 'line',
      smooth: true,
      showSymbol: snapshots.length < 30,
      areaStyle: { opacity: 0.12 },
      lineStyle: { width: 2 },
      data: snapshots.map((s) => (currency === 'CNY' ? s.total_cny : s.total_usd)),
    }],
  }

  const byCur = (code) => summary?.by_currency?.find((c) => c.currency === code)

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      {/* 顶部：总额 + 今日涨跌 + 累计盈亏 + 币种切换 + 更新按钮 */}
      <Card loading={loading}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} md={14}>
            <Space direction="vertical" size={4}>
              <span style={{ color: '#888' }}>总资产（{CURRENCY_LABEL[currency]}）</span>
              <span style={{ fontSize: 40, fontWeight: 700, lineHeight: 1.1 }}>
                {sym}{fmt(summary?.total)}
              </span>
              <Space size={16} wrap>
                <Space size={4}>
                  <span style={{ color: changeColor, fontSize: 16 }}>
                    {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {sym}{fmt(Math.abs(change))}
                  </span>
                  <span style={{ color: changeColor }}>({up ? '+' : ''}{summary?.change_pct ?? 0}%)</span>
                  <span style={{ color: '#aaa' }}>今日</span>
                </Space>
                <Space size={4}>
                  <span style={{ color: profitColor, fontSize: 16 }}>
                    {profitUp ? '+' : ''}{sym}{fmt(totalProfit)}
                  </span>
                  <span style={{ color: profitColor }}>({profitUp ? '+' : ''}{summary?.profit_pct ?? 0}%)</span>
                  <Tooltip title="市值 − 成本，仅统计填了成本价的资产">
                    <span style={{ color: '#aaa' }}>累计盈亏</span>
                  </Tooltip>
                </Space>
              </Space>
            </Space>
          </Col>
          <Col xs={24} md={10} style={{ textAlign: 'right' }}>
            <Space direction="vertical" align="end" size={12}>
              <Segmented
                value={currency}
                onChange={setCurrency}
                options={[{ label: '¥ 人民币', value: 'CNY' }, { label: '$ 美元', value: 'USD' }]}
              />
              <Button type="primary" icon={<ReloadOutlined />} loading={refreshing} onClick={doRefresh}>
                更新行情
              </Button>
              <Tooltip title="1 美元 = ? 人民币">
                <Tag>汇率 USD/CNY: {summary?.rate ?? '—'}</Tag>
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 人民币资产 / 美元资产 分开 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12}>
          <Card loading={loading} title="人民币资产 ¥">
            <div style={{ fontSize: 24, fontWeight: 600 }}>¥{fmt(byCur('CNY')?.native_total ?? 0)}</div>
            <div style={{ marginTop: 8, color: '#888' }}>折合 {sym}{fmt(byCur('CNY')?.display_total)}</div>
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card loading={loading} title="美元资产 $">
            <div style={{ fontSize: 24, fontWeight: 600 }}>${fmt(byCur('USD')?.native_total ?? 0)}</div>
            <div style={{ marginTop: 8, color: '#888' }}>折合 {sym}{fmt(byCur('USD')?.display_total)}</div>
          </Card>
        </Col>
      </Row>

      {/* 总资产走势 */}
      <Card loading={loading} title="总资产走势">
        {snapshots.length > 1 ? (
          <ReactECharts option={trendOption} style={{ height: 300 }} notMerge />
        ) : (
          <Empty description="走势需要至少 2 天的数据，明天再来看看～（每天打开总览会自动记录一个点）" />
        )}
      </Card>

      {/* 占比：按平台 + 按类型 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card loading={loading} title="平台占比">
            {summary?.by_platform?.length ? (
              <ReactECharts option={pie(summary.by_platform, 'platform')} style={{ height: 300 }} notMerge />
            ) : (
              <Empty description={<span>还没有资产，去 <Link to="/platforms">平台管理</Link> 添加</span>} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card loading={loading} title="类型占比">
            {summary?.by_type?.length ? (
              <ReactECharts option={pie(summary.by_type, 'asset_type', (t) => ASSET_TYPE_LABEL[t] || t)} style={{ height: 300 }} notMerge />
            ) : (
              <Empty description="还没有资产" />
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
