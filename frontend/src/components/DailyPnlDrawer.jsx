import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Drawer, Empty, Grid, List, Segmented, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { getDailyPnl } from '../api'
import { CURRENCY_SYMBOL, fmt } from '../constants'
import { useColorScheme } from '../colorScheme.jsx'

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

export default function DailyPnlDrawer({ open, onClose, currency, masked, refreshKey }) {
  const [view, setView] = useState('calendar')
  const [month, setMonth] = useState(() => { const t = new Date(); return { y: t.getUTCFullYear(), m: t.getUTCMonth() } })
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [revision, setRevision] = useState(0)
  const { upColor, downColor } = useColorScheme()
  const screens = Grid.useBreakpoint()

  const todayStr = new Date().toISOString().slice(0, 10)
  const todayY = parseInt(todayStr.slice(0, 4), 10)
  const todayM = parseInt(todayStr.slice(5, 7), 10) - 1

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    getDailyPnl({ days: 366, currency }).then((value) => {
      if (active) setData(value)
    }).catch(() => { if (active) setError('每日盈亏加载失败，请重试') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, currency, revision, refreshKey])

  const money = (v) => masked ? '****' : `${v > 0 ? '+' : ''}${CURRENCY_SYMBOL[currency]}${fmt(v)}`

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
    for (let r = 0; r < rows; r++) {
      const line = []
      for (let wd = 0; wd < 7; wd++) {
        const dayNum = r * 7 + wd - startDow + 1
        if (dayNum < 1 || dayNum > daysInMonth) { line.push(null); continue }
        const key = toDay(new Date(Date.UTC(month.y, month.m, dayNum)))
        const item = byDay[key]
        line.push({ dayNum, key, item, weekend: wd >= 5 })
        if (item && item.pnl != null) { total += item.pnl; hasTotal = true }
      }
      cells.push(line)
    }
    return { cells, total, hasTotal }
  }, [month, byDay])

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
        </Space>
        {cal.hasTotal && (
          <Typography.Text strong style={{ color: masked ? undefined : cal.total > 0 ? upColor : cal.total < 0 ? downColor : undefined, fontSize: 14 }}>
            本月 {money(cal.total)}
          </Typography.Text>
        )}
      </div>
      {/* 星期表头 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6, marginBottom: 4 }}>
        {WEEKDAYS.map((wd) => (
          <div key={wd} style={{ textAlign: 'center', fontSize: 12, color: '#8c8c8c', padding: '2px 0' }}>{wd}</div>
        ))}
      </div>
      {/* 日期格 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6 }}>
        {cal.cells.flat().map((cell, i) => {
          if (!cell) return <div key={i} style={{ minHeight: 54 }} />
          const pnl = cell.item?.pnl ?? null
          const color = pnl == null ? undefined : masked ? undefined : pnl > 0 ? upColor : pnl < 0 ? downColor : '#8c8c8c'
          const isToday = cell.key === todayStr
          return (
            <Tooltip key={i} title={cellTooltip(cell)} mouseEnterDelay={0.05}>
              <div style={{
                minHeight: 54, borderRadius: 8, padding: '4px 6px', cursor: 'default',
                background: isToday ? 'rgba(22,119,255,0.06)' : cell.weekend ? 'rgba(0,0,0,0.02)' : 'transparent',
                border: isToday ? '1px solid #1677ff' : '1px solid transparent',
                boxSizing: 'border-box',
              }}>
                <div style={{ fontSize: 11, lineHeight: '16px', color: cell.weekend ? '#bfbfbf' : '#8c8c8c' }}>{cell.dayNum}</div>
                {pnl != null && (
                  <div style={{ fontSize: 12, fontWeight: 600, lineHeight: '22px', color, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {masked ? '·' : compact(pnl)}
                  </div>
                )}
              </div>
            </Tooltip>
          )
        })}
      </div>
      <div style={{ marginTop: 10, fontSize: 12, color: '#8c8c8c' }}>
        红涨绿跌 · 悬停看明细 · 灰字为零或无变化
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
          <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>更新于 {new Date(row.updated_at).toLocaleString('zh-CN')}</Typography.Text></div>
        </List.Item>
      )}
    />
  ) : (
    <Table rowKey="day" loading={loading} dataSource={data?.items || []} size="middle"
      pagination={{ pageSize: 15, hideOnSinglePage: true }} scroll={{ x: 450 }}
      locale={{ emptyText: <Empty description="尚无每日盈亏记录；自动刷新后开始建立基准，历史不会补零。" /> }}
      columns={[
        { title: '日期（UTC）', dataIndex: 'day', render: (day, row) => <span>{day}{row.provisional && <Tag style={{ marginLeft: 6 }}>今日暂计</Tag>}</span> },
        { title: `盈亏（${currency}）`, dataIndex: 'pnl', align: 'right', render: (v) => v == null ? <Typography.Text type="secondary">待确认</Typography.Text> : <span style={{ fontWeight: 600, color: masked ? undefined : v > 0 ? upColor : v < 0 ? downColor : undefined }}>{money(v)}</span> },
        { title: '状态', dataIndex: 'status', render: (value, row) => <Tag title={row.note}>{labels[value] || value}</Tag> },
      ]}
      expandable={{ expandedRowRender: (row) => <Typography.Text type="secondary">{row.note}<br />更新于 {new Date(row.updated_at).toLocaleString('zh-CN')}</Typography.Text> }}
    />
  )

  return (
    <Drawer title="每日盈亏" open={open} onClose={onClose} width="min(720px, 100vw)">
      <Space direction="vertical" size={16} style={{ display: 'flex' }}>
        <div>
          <Typography.Title level={4} style={{ margin: '0 0 8px' }}>把每天的变化留下来</Typography.Title>
          <Typography.Text type="secondary">后台每日自动记录，登录后再更新一次。历史金额使用记录时的汇率。</Typography.Text>
        </div>
        {screens.sm && (
          <Segmented value={view} onChange={setView} options={[
            { label: '日历', value: 'calendar' }, { label: '列表', value: 'list' },
          ]} />
        )}
        {error ? <Alert type="error" showIcon message={error} action={<Button onClick={() => setRevision((v) => v + 1)}>重试</Button>} />
          : view === 'calendar' && screens.sm ? calendarView : listView}
        <Alert type="info" showIcon message="统计口径"
          description={data?.method || '累计持仓收益的日变化，含已实现盈亏和分红；排除入出金和汇兑变动。首日或缺少价格、成本时不显示虚构盈亏。'} />
      </Space>
    </Drawer>
  )
}
