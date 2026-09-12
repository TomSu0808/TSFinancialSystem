import { useEffect, useState } from 'react'
import { Alert, Button, Drawer, Empty, Grid, List, Segmented, Space, Table, Tag, Typography } from 'antd'
import { getDailyPnl } from '../api'
import { CURRENCY_SYMBOL, fmt } from '../constants'
import { useColorScheme } from '../colorScheme.jsx'

const labels = { recorded: '已记录', baseline: '建立基准', missing: '数据不足', stale: '待更新', adjusted: '口径变更' }

export default function DailyPnlDrawer({ open, onClose, currency, masked, refreshKey }) {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [revision, setRevision] = useState(0)
  const { upColor, downColor } = useColorScheme()
  const screens = Grid.useBreakpoint()
  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    getDailyPnl({ days, currency }).then((value) => {
      if (active) setData(value)
    }).catch(() => { if (active) setError('每日盈亏加载失败，请重试') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, days, currency, revision, refreshKey])
  const money = (v) => masked ? '****' : `${v > 0 ? '+' : ''}${CURRENCY_SYMBOL[currency]}${fmt(v)}`
  return (
    <Drawer title="每日盈亏" open={open} onClose={onClose} width="min(700px, 100vw)">
      <Space direction="vertical" size={16} style={{ display: 'flex' }}>
        <div>
          <Typography.Title level={4} style={{ margin: '0 0 8px' }}>把每天的变化留下来</Typography.Title>
          <Typography.Text type="secondary">后台每日自动记录，登录后再更新一次。历史金额使用记录时的汇率。</Typography.Text>
        </div>
        <Segmented value={days} onChange={setDays} options={[
          { label: '近 30 天', value: 30 }, { label: '近 90 天', value: 90 }, { label: '近一年', value: 365 },
        ]} />
        {error ? <Alert type="error" showIcon message={error} action={<Button onClick={() => setRevision((v) => v + 1)}>重试</Button>} /> : !screens.sm ? (
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
        )}
        <Alert type="info" showIcon message="统计口径"
          description={data?.method || '累计持仓收益的日变化，含已实现盈亏和分红；排除入出金和汇兑变动。首日或缺少价格、成本时不显示虚构盈亏。'} />
      </Space>
    </Drawer>
  )
}
