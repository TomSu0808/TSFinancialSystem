import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, Col, Divider, Empty, Row, Segmented, Space, Steps, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  ReloadOutlined, ArrowUpOutlined, ArrowDownOutlined,
  EditOutlined, InfoCircleOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, RightOutlined, WarningOutlined, BellOutlined,
  ThunderboltOutlined, PlusOutlined, UploadOutlined,
} from '@ant-design/icons'

const { Title, Text } = Typography
import ReactECharts from 'echarts-for-react'
import { getSummary, getSnapshots, refreshPrices, refreshRate, getAutomationStatus, runNow, listAlertEvents } from '../api'
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
  const [automationStatus, setAutomationStatus] = useState(null)
  const [unreadAlerts, setUnreadAlerts] = useState([])
  const [runningNow, setRunningNow] = useState(false)

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
    // 异步加载自动化状态和未读提醒（不影响主流程）
    getAutomationStatus().then(setAutomationStatus).catch(() => {})
    listAlertEvents({ status: 'unread', limit: 3 }).then(setUnreadAlerts).catch(() => {})
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

  const doRunNow = async () => {
    setRunningNow(true)
    try {
      const run = await runNow()
      message.success(
        `自动刷新完成：${run.holdings_updated}/${run.holdings_total} 条行情，快照已保存`
      )
      await load()
    } catch (e) {
      if (e.response?.status === 409) {
        message.warning('刷新任务正在执行中，请稍后再试')
      } else {
        message.error('执行失败：' + (e.response?.data?.detail || e.message))
      }
    } finally {
      setRunningNow(false)
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
      {/* 页面标题与说明 */}
      <div style={{ marginBottom: -8 }}>
        <Title level={3} style={{ marginTop: 0, marginBottom: 4, fontWeight: 700 }}>
          投资总览
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          统一查看账户、持仓、收益、现金和 AI 投研状态
        </Text>
        {/* CTA 操作按钮 */}
        <Space size={8} wrap style={{ marginTop: 16 }}>
          <Button
            type="default"
            icon={<PlusOutlined />}
            onClick={() => navigate('/platforms', { state: { openAdd: true } })}
          >
            创建账户
          </Button>
          <Button
            type="default"
            icon={<EditOutlined />}
            onClick={() => navigate('/transactions', { state: { openAdd: true } })}
          >
            记录交易
          </Button>
          <Button
            style={{ color: '#1677ff', borderColor: '#1677ff' }}
            icon={<UploadOutlined />}
            onClick={() => navigate('/transactions')}
          >
            导入交易
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => navigate('/research')}
          >
            AI 投研
          </Button>
        </Space>
      </div>

      <Card loading={loading} styles={{ body: { padding: 24 } }}>
        <Row gutter={[24, 24]} align="middle">
          <Col xs={24} md={15}>
            <div style={{ color: '#8c8c8c', marginBottom: 8, fontSize: 13, fontWeight: 500 }}>
              总资产（{CURRENCY_LABEL[displayCurrency]}）
            </div>
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
        <Card
          style={{
            borderColor: '#1677ff22',
            background: 'linear-gradient(135deg, #f6f8fb 0%, #e6f4ff 100%)',
          }}
        >
          <Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>
            开始使用
          </Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 20, fontSize: 13 }}>
            按以下三步开始记录你的资产状况，每一步都会自动打开对应功能页面。
          </Text>
          <Steps
            direction="vertical"
            size="small"
            current={0}
            style={{ maxWidth: 560 }}
            items={[
              {
                title: '创建账户 — 添加券商、银行或钱包',
                description: (
                  <span>
                    先在账户页添加你使用的平台，支持股票、基金、加密货币和现金账户。
                    {' '}
                    <Link to="/platforms" style={{ fontWeight: 500 }}>
                      去创建 <RightOutlined style={{ fontSize: 11 }} />
                    </Link>
                  </span>
                ),
                status: 'process',
              },
              {
                title: '记录或导入交易 — 系统自动生成持仓和成本',
                description: (
                  <span>
                    记录买入、卖出、入金等交易流水，平台会自动计算持仓数量和成本基准。
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
                title: '查看总览与笔记 — 跟踪收益、配置和 AI 报告',
                description:
                  '有了数据之后，回到这里查看资产分布、收益走势和今日变化。也可以生成 AI 投研报告，并记录为投资笔记。',
                status: 'wait',
              },
            ]}
          />
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 20 }}
            message="提示"
            description="在右上角「个人资料」中设置 AI API Key 后即可使用 AI 投研功能。也可以随时导出备份保护你的数据。"
          />
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

      {/* 今日归因 / 数据状态 */}
      {summary && total > 0 && (
        <Card title="今日归因 / 数据状态" loading={loading} size="small">
          <Row gutter={[24, 16]}>
            {/* 今日涨跌贡献 */}
            <Col xs={24} md={12}>
              <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>今日涨跌贡献</div>
              {summary.top_movers?.length ? (
                <Space direction="vertical" style={{ display: 'flex' }} size={6}>
                  {summary.top_movers.map((m) => {
                    const up = m.display_change >= 0
                    const color = up ? RED : GREEN
                    return (
                      <div key={m.holding_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 13 }}>
                        <Space size={4}>
                          <span>{m.name || m.symbol || '—'}</span>
                          {m.symbol && m.name && (
                            <span style={{ color: '#aaa', fontSize: 11 }}>{m.symbol}</span>
                          )}
                          <Tag style={{ fontSize: 11, padding: '0 4px' }}>{m.platform}</Tag>
                        </Space>
                        <Space size={6}>
                          <span style={{ color, fontWeight: 600 }}>
                            {up ? '+' : ''}{sym}{fmt(Math.abs(m.display_change))}
                          </span>
                          <span style={{ color, fontSize: 12 }}>
                            ({up ? '+' : ''}{m.change_pct?.toFixed(2)}%)
                          </span>
                        </Space>
                      </div>
                    )
                  })}
                </Space>
              ) : (
                <div style={{ color: '#aaa', fontSize: 13 }}>
                  暂无价格变动数据（刷新行情后显示）
                </div>
              )}
            </Col>

            {/* 收益组成 + 行情状态 */}
            <Col xs={24} md={12}>
              {/* 收益组成 */}
              <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>收益组成</div>
              <Row gutter={[8, 8]} style={{ marginBottom: 16 }}>
                {[
                  { label: '未实现盈亏', value: summary.return_breakdown?.unrealized_pnl ?? 0 },
                  { label: '已实现盈亏', value: summary.return_breakdown?.realized_pnl ?? 0 },
                  { label: '分红/利息', value: summary.return_breakdown?.realized_income ?? 0 },
                  { label: '总收益', value: summary.return_breakdown?.total_return ?? 0 },
                ].map(({ label, value }) => (
                  <Col xs={12} key={label}>
                    <div style={{ color: '#8c8c8c', fontSize: 12 }}>{label}</div>
                    <div style={{ color: value >= 0 ? RED : GREEN, fontWeight: 600, fontSize: 13 }}>
                      {value >= 0 ? '+' : ''}{sym}{fmt(Math.abs(value))}
                    </div>
                  </Col>
                ))}
              </Row>

              {/* 行情数据状态 */}
              <Divider style={{ margin: '8px 0' }} />
              <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>行情状态</div>
              {(() => {
                const df = summary.data_freshness
                if (!df) return null
                return (
                  <Space direction="vertical" style={{ display: 'flex' }} size={6}>
                    <div style={{ fontSize: 13, color: '#555' }}>
                      已有行情 <b>{df.priced_count}</b> 条
                      {df.stale_count > 0 && (
                        <span style={{ color: '#faad14', marginLeft: 8 }}>
                          <WarningOutlined /> 过期/缺失 {df.stale_count} 条
                        </span>
                      )}
                    </div>
                    {df.stale_count > 0 && df.stale_items?.length > 0 && (
                      <div style={{ background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 4, padding: '6px 10px' }}>
                        <div style={{ fontSize: 12, color: '#875500', marginBottom: 4 }}>行情过期或未获取的持仓：</div>
                        {df.stale_items.map((item, i) => (
                          <div key={i} style={{ fontSize: 12, color: '#6b4c00' }}>
                            {item.name || item.symbol || '—'}
                            {item.symbol && item.name ? ` (${item.symbol})` : ''}
                            · {item.platform} · {item.currency}
                            {item.price_updated_at
                              ? <span style={{ color: '#aaa' }}> · 最后更新 {item.price_updated_at.slice(0, 10)}</span>
                              : <span style={{ color: '#aaa' }}> · 未获取</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </Space>
                )
              })()}
            </Col>
          </Row>
        </Card>
      )}

      {/* 自动刷新状态 */}
      {automationStatus && (
        <Card
          size="small"
          title={
            <Space size={6}>
              <ThunderboltOutlined style={{ color: automationStatus.enabled ? '#1677ff' : '#aaa' }} />
              自动刷新
              {automationStatus.enabled
                ? <Tag color="blue">已启用 · {automationStatus.schedule_time}</Tag>
                : <Tag>未启用</Tag>}
            </Space>
          }
          extra={
            <Button size="small" loading={runningNow} onClick={doRunNow}>
              立即运行
            </Button>
          }
        >
          {automationStatus.last_run ? (
            <Space size={16} wrap style={{ fontSize: 12, color: '#595959' }}>
              <span>
                状态：
                <Tag color={
                  automationStatus.last_run.status === 'success' ? 'success'
                  : automationStatus.last_run.status === 'partial_failed' ? 'warning'
                  : 'error'
                }>
                  {automationStatus.last_run.status === 'success' ? '成功'
                   : automationStatus.last_run.status === 'partial_failed' ? '部分失败'
                   : '失败'}
                </Tag>
              </span>
              <span>行情：{automationStatus.last_run.holdings_updated}/{automationStatus.last_run.holdings_total}</span>
              <span>快照：{automationStatus.last_run.snapshots_saved}</span>
              {automationStatus.last_run.finished_at && (
                <span>
                  完成于 {new Date(automationStatus.last_run.finished_at).toLocaleString('zh-CN', {
                    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                  })}
                </span>
              )}
            </Space>
          ) : (
            <span style={{ fontSize: 12, color: '#aaa' }}>
              {automationStatus.enabled ? '尚未执行过自动刷新任务' : '启用自动刷新后，系统将每日定时刷新行情和汇率'}
            </span>
          )}
        </Card>
      )}

      {/* 提醒摘要 */}
      {unreadAlerts.length > 0 && (
        <Card
          size="small"
          title={
            <Space size={6}>
              <BellOutlined style={{ color: '#faad14' }} />
              <span>未读提醒</span>
              <Tag color="orange">{unreadAlerts.length} 条</Tag>
            </Space>
          }
          extra={<Link to="/alerts" style={{ fontSize: 12 }}>查看全部 &rsaquo;</Link>}
        >
          <Space direction="vertical" style={{ display: 'flex' }} size={6}>
            {unreadAlerts.map((ev) => (
              <div key={ev.id} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                <ExclamationCircleOutlined style={{ color: '#faad14', marginTop: 2, flexShrink: 0 }} />
                <div>
                  <span style={{ fontWeight: 500 }}>{ev.title}</span>
                  <span style={{ color: '#8c8c8c', marginLeft: 8 }}>{ev.message}</span>
                </div>
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
