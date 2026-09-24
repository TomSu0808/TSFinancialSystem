import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Drawer, Empty, Grid, List, Segmented, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { ArrowLeftOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { getDailyPnl, getDailyPnlDetail } from '../api'
import { CURRENCY_SYMBOL, ASSET_TYPE_LABEL, fmt } from '../constants'
import { useColorScheme } from '../colorScheme.jsx'
import { useDisplaySettings } from '../displaySettings.jsx'

const labels = { recorded: '已记录', baseline: '建立基准', missing: '数据不足', stale: '待更新', adjusted: '口径变更' }
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

function parseDay(s) {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
const addDays = (d, n) => new Date(d.getTime() + n * 86400000)
const toDay = (d) => d.toISOString().slice(0, 10)
const dow = (d) => (d.getUTCDay() + 6) % 7 // 周一 = 0

// 格内金额紧凑显示：+1,234 / -567 / +1.2万
function compact(v) {
  const a = Math.abs(v)
  let s
  if (a >= 1e8) s = (a / 1e8).toFixed(2) + '亿'
  else if (a >= 1e4) s = (a / 1e4).toFixed(1) + '万'
  else if (a >= 100) s = Math.round(a).toLocaleString('zh-CN')
  else s = a.toFixed(a % 1 ? 1 : 0)
  return (v > 0 ? '+' : v < 0 ? '-' : '') + s
}

export default function DailyPnlDrawer({ open, onClose, masked, refreshKey }) {
  const { displayCurrency, setDisplayCurrency } = useDisplaySettings()
  const [view, setView] = useState('calendar')
  const [month, setMonth] = useState(() => { const t = new Date(); return { y: t.getUTCFullYear(), m: t.getUTCMonth() } })
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [revision, setRevision] = useState(0)
  const [selectedDay, setSelectedDay] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(null)
  const [detailRevision, setDetailRevision] = useState(0)
  const { upColor, downColor } = useColorScheme()
  const screens = Grid.useBreakpoint()
  const isMobile = !screens.sm

  const todayStr = new Date().toISOString().slice(0, 10)
  const todayY = parseInt(todayStr.slice(0, 4), 10)
  const todayM = parseInt(todayStr.slice(5, 7), 10) - 1

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    getDailyPnl({ days: 366, currency: displayCurrency }).then((value) => {
      if (active) setData(value)
    }).catch(() => { if (active) setError('每日盈亏加载失败，请重试') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, displayCurrency, revision, refreshKey])

  useEffect(() => {
    if (!open || view !== 'detail' || !selectedDay) return
    let active = true
    setDetailLoading(true)
    setDetailError(null)
    setDetail(null)
    getDailyPnlDetail(selectedDay, { currency: displayCurrency }).then((value) => {
      if (active) setDetail(value)
    }).catch(() => { if (active) setDetailError('明细加载失败，请重试') })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [open, view, selectedDay, displayCurrency, detailRevision])

  const money = (v) => masked ? '****' : `${v > 0 ? '+' : ''}${CURRENCY_SYMBOL[displayCurrency]}${fmt(v)}`
  const moneyOrPending = (v) => (v == null ? '待确认' : money(v))

  const openDetail = (day) => {
    setSelectedDay(day)
    setView('detail')
  }

  const byDay = useMemo(() => {
    const m = {}
    for (const it of data?.items || []) m[it.day] = it
    return m
  }, [data])

  const cal = useMemo(() => {
    const first = new Date(Date.UTC(month.y, month.m, 1))
    const startDow = dow(first)
    const daysInMonth = new Date(Date.UTC(month.y, month.m + 1, 0)).getUTCDate()
    const rows = Math.ceil((startDow + daysInMonth) / 7)
    const cells = []
    let total = 0
    let hasTotal = false
    let recorded = 0
    let pastDays = 0
    for (let r = 0; r < rows; r++) {
      const line = []
      for (let wd = 0; wd < 7; wd++) {
        const dayNum = r * 7 + wd - startDow + 1
        if (dayNum < 1 || dayNum > daysInMonth) { line.push(null); continue }
        const key = toDay(new Date(Date.UTC(month.y, month.m, dayNum)))
        const item = byDay[key]
        line.push({ dayNum, key, item, weekend: wd >= 5 })
        const isFuture = key > todayStr
        if (!isFuture) pastDays++
        if (item && item.pnl != null) { total += item.pnl; hasTotal = true; recorded++ }
      }
      cells.push(line)
    }
    return { cells, total, hasTotal, recorded, incomplete: recorded < pastDays }
  }, [month, byDay, todayStr])

  const isCurrentMonth = month.y === todayY && month.m === todayM
  const shiftMonth = (delta) => setMonth((m) => {
    const d = new Date(Date.UTC(m.y, m.m + delta, 1))
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() }
  })

  const cellTooltip = (cell) => {
    const it = cell.item
    if (!it) return `${cell.key} · 无记录`
    return (
      <Space direction="vertical" size={0}>
        <Typography.Text strong>{cell.key}{it.provisional ? ' · 今日暂计' : ''}</Typography.Text>
        <Typography.Text>{it.pnl == null ? '待确认' : money(it.pnl)}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{labels[it.status] || it.status}</Typography.Text>
        {it.note && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{it.note}</Typography.Text>}
      </Space>
    )
  }

  const calendarView = (
    <div style={{ opacity: loading ? 0.45 : 1, transition: 'opacity .2s' }}>
      {/* 月份导航 + 当月合计 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Space size={4}>
          <Button type="text" size="small" icon={<LeftOutlined />} onClick={() => shiftMonth(-1)} />
          <Typography.Text strong style={{ fontSize: 15 }}>{month.y}年{month.m + 1}月</Typography.Text>
          <Button type="text" size="small" icon={<RightOutlined />} disabled={isCurrentMonth} onClick={() => shiftMonth(1)} />
          {!isCurrentMonth && (
            <Button type="link" size="small" onClick={() => setMonth({ y: todayY, m: todayM })}>回到本月</Button>
          )}
        </Space>
        {cal.hasTotal ? (
          <Space size={6} align="center" wrap>
            <Typography.Text strong style={{ color: masked ? undefined : cal.total > 0 ? upColor : cal.total < 0 ? downColor : undefined, fontSize: 14 }}>
              本月 {money(cal.total)}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>已记录 {cal.recorded} 天</Typography.Text>
            {cal.incomplete && <Tag color="orange" style={{ fontSize: 11, marginInlineEnd: 0 }}>数据不完整</Tag>}
          </Space>
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>本月暂无记录</Typography.Text>
        )}
      </div>
      {/* 星期表头 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: isMobile ? 4 : 6, marginBottom: 4 }}>
        {WEEKDAYS.map((wd) => (
          <div key={wd} style={{ textAlign: 'center', fontSize: isMobile ? 11 : 12, color: '#8c8c8c', padding: '2px 0' }}>{wd}</div>
        ))}
      </div>
      {/* 日期格 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: isMobile ? 4 : 6 }}>
        {cal.cells.flat().map((cell, i) => {
          if (!cell) return <div key={i} style={{ minHeight: 54 }} />
          const it = cell.item
          const pnl = it?.pnl ?? null
          const color = pnl == null ? undefined : masked ? undefined : pnl > 0 ? upColor : pnl < 0 ? downColor : '#8c8c8c'
          const isToday = cell.key === todayStr
          const isSelected = cell.key === selectedDay
          const isFuture = cell.key > todayStr
          const clickable = !!it
          const statusText = it && pnl == null
            ? (it.status === 'recorded' ? '待确认' : labels[it.status] || it.status)
            : null
          const noRecord = !it && !isFuture
          return (
            <Tooltip key={i} title={cellTooltip(cell)} mouseEnterDelay={0.05}>
              <div
                onClick={clickable ? () => openDetail(cell.key) : undefined}
                style={{
                  minHeight: 54, borderRadius: 8, padding: '4px 6px',
                  cursor: clickable ? 'pointer' : 'default',
                  background: isToday ? 'rgba(22,119,255,0.06)' : isSelected ? 'rgba(250,140,22,0.10)' : cell.weekend ? 'rgba(0,0,0,0.02)' : 'transparent',
                  border: isToday ? '1px solid #1677ff' : isSelected ? '1px solid #ffa940' : '1px solid transparent',
                  boxSizing: 'border-box',
                }}
              >
                <div style={{ fontSize: isMobile ? 11 : 12, lineHeight: '16px', color: isFuture ? '#d9d9d9' : cell.weekend ? '#bfbfbf' : '#8c8c8c' }}>{cell.dayNum}</div>
                {pnl != null ? (
                  <div style={{ fontSize: 12, fontWeight: 600, lineHeight: '22px', color, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {masked ? '·' : compact(pnl)}
                  </div>
                ) : statusText ? (
                  <div style={{ fontSize: isMobile ? 10 : 11, lineHeight: '20px', color: '#bfbfbf', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{statusText}</div>
                ) : noRecord ? (
                  <div style={{ fontSize: 11, lineHeight: '20px', color: '#d9d9d9' }}>—</div>
                ) : null}
              </div>
            </Tooltip>
          )
        })}
      </div>
      <div style={{ marginTop: 10, fontSize: 12, color: '#8c8c8c' }}>
        点击日期看逐仓位明细 · 灰字为零或无变化 · — 为无记录（涨跌颜色随显示设置）
      </div>
    </div>
  )

  const listView = !screens.sm ? (
    <List loading={loading} dataSource={data?.items || []}
      pagination={{ pageSize: 15, hideOnSinglePage: true, simple: true }}
      locale={{ emptyText: <Empty description="暂无记录，自动刷新后开始建立基准" /> }}
      renderItem={(row) => (
        <List.Item style={{ display: 'block', padding: '16px 0' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8 }}>
            <Typography.Text strong>{row.day} <Typography.Text type="secondary">UTC</Typography.Text></Typography.Text>
            <strong style={{ color: masked ? undefined : row.pnl > 0 ? upColor : row.pnl < 0 ? downColor : undefined, overflowWrap: 'anywhere' }}>
              {row.pnl == null ? '待确认' : money(row.pnl)}
            </strong>
          </div>
          <div style={{ margin: '8px 0' }}><Tag>{labels[row.status] || row.status}</Tag>{row.provisional && <Tag>今日暂计</Tag>}</div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.note}</Typography.Text>
          <div style={{ marginTop: 6 }}>
            <Button size="small" type="link" style={{ padding: 0 }} onClick={() => openDetail(row.day)}>查看明细</Button>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>更新于 {new Date(row.updated_at).toLocaleString('zh-CN')}</Typography.Text>
          </div>
        </List.Item>
      )}
    />
  ) : (
    <Table rowKey="day" loading={loading} dataSource={data?.items || []} size="middle"
      pagination={{ pageSize: 15, hideOnSinglePage: true }} scroll={{ x: 450 }}
      locale={{ emptyText: <Empty description="尚无每日盈亏记录；自动刷新后开始建立基准，历史不会补零。" /> }}
      columns={[
        { title: '日期（UTC）', dataIndex: 'day', render: (day, row) => <span>{day}{row.provisional && <Tag style={{ marginLeft: 6 }}>今日暂计</Tag>}</span> },
        { title: `盈亏（${displayCurrency}）`, dataIndex: 'pnl', align: 'right', render: (v) => v == null ? <Typography.Text type="secondary">待确认</Typography.Text> : <span style={{ fontWeight: 600, color: masked ? undefined : v > 0 ? upColor : v < 0 ? downColor : undefined }}>{money(v)}</span> },
        { title: '状态', dataIndex: 'status', render: (value, row) => <Tag title={row.note}>{labels[value] || value}</Tag> },
        { title: '', dataIndex: 'day', align: 'right', render: (day) => <Button size="small" type="link" onClick={() => openDetail(day)}>查看明细</Button> },
      ]}
      expandable={{ expandedRowRender: (row) => <Typography.Text type="secondary">{row.note}<br />更新于 {new Date(row.updated_at).toLocaleString('zh-CN')}</Typography.Text> }}
    />
  )

  const detailView = (
    <div>
      <Space direction="vertical" size={12} style={{ display: 'flex' }}>
        <Space size={4}>
          <Button size="small" type="text" icon={<ArrowLeftOutlined />} onClick={() => setView('calendar')}>返回</Button>
          <Typography.Text strong>{selectedDay}</Typography.Text>
          <Typography.Text type="secondary">UTC</Typography.Text>
        </Space>
        {detailError ? (
          <Alert type="error" showIcon message={detailError} action={<Button size="small" onClick={() => setDetailRevision((v) => v + 1)}>重试</Button>} />
        ) : detailLoading || !detail ? (
          <Empty description="正在加载明细…" />
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
              <Space size={8} wrap>
                <Tag>{labels[detail.status] || detail.status}</Tag>
                {detail.excluded_count > 0 && <Tag color="orange">部分持仓缺价/成本</Tag>}
                {detail.rounding_diff !== 0 && <Tag color="default">有舍入差</Tag>}
              </Space>
              <Typography.Text strong style={{ fontSize: 16, color: detail.total == null ? undefined : masked ? undefined : detail.total > 0 ? upColor : detail.total < 0 ? downColor : undefined }}>
                当日总盈亏 {moneyOrPending(detail.total)}
              </Typography.Text>
            </div>
            {detail.note && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{detail.note}</Typography.Text>}
            {!detail.has_details ? (
              <Empty description={detail.no_detail_message} />
            ) : detail.positions.length === 0 ? (
              <Empty description="该日无持仓明细" />
            ) : (
              <List
                dataSource={detail.positions}
                renderItem={(p) => {
                  const color = p.pnl == null ? undefined : masked ? undefined : p.pnl > 0 ? upColor : p.pnl < 0 ? downColor : undefined
                  return (
                    <List.Item style={{ display: 'block', padding: '12px 0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                        <Space size={6} wrap>
                          <Tag style={{ fontSize: 11, padding: '0 4px' }}>{p.platform}</Tag>
                          <span>{p.name || p.symbol || '—'}</span>
                          {p.symbol && p.name && <span style={{ color: '#aaa', fontSize: 12 }}>{p.symbol}</span>}
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{ASSET_TYPE_LABEL[p.asset_type] || p.asset_type}</Typography.Text>
                        </Space>
                        <strong style={{ color }}>{moneyOrPending(p.pnl)}</strong>
                      </div>
                      {p.pnl_native != null && p.currency !== displayCurrency && (
                        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                          原币 {masked ? '****' : `${CURRENCY_SYMBOL[p.currency]}${fmt(p.pnl_native)}`}（{p.currency}）
                        </div>
                      )}
                      {p.reason && <div style={{ fontSize: 12, color: '#bfbfbf', marginTop: 2 }}>{p.reason}</div>}
                    </List.Item>
                  )
                }}
              />
            )}
          </>
        )}
      </Space>
    </div>
  )

  return (
    <Drawer title="每日盈亏" open={open} onClose={onClose} width="min(720px, 100vw)">
      <Space direction="vertical" size={16} style={{ display: 'flex' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <Typography.Title level={4} style={{ margin: '0 0 8px' }}>把每天的变化留下来</Typography.Title>
            <Typography.Text type="secondary">后台每日自动记录，登录后再更新一次。历史金额使用记录时的汇率。</Typography.Text>
          </div>
          <Segmented
            value={displayCurrency}
            onChange={setDisplayCurrency}
            options={[{ label: '¥ 人民币', value: 'CNY' }, { label: '$ 美元', value: 'USD' }]}
          />
        </div>
        {view === 'detail' ? detailView : (
          <>
            {screens.sm && (
              <Segmented value={view} onChange={setView} options={[
                { label: '日历', value: 'calendar' }, { label: '列表', value: 'list' },
              ]} />
            )}
            {error ? <Alert type="error" showIcon message={error} action={<Button onClick={() => setRevision((v) => v + 1)}>重试</Button>} />
              : view === 'calendar' ? calendarView : listView}
          </>
        )}
        <Alert type="info" showIcon message="统计口径"
          description={data?.method || '累计持仓收益的日变化，含已实现盈亏和分红；排除入出金和汇兑变动。首日或缺少价格、成本时不显示虚构盈亏。与总览「今日涨跌」（仅当日价格变动）口径不同。'} />
      </Space>
    </Drawer>
  )
}
