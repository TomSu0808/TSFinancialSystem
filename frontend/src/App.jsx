import { useEffect, useRef, useState } from 'react'
import {
  Layout, Menu, Dropdown, Avatar, Space, Modal, message, ConfigProvider, theme,
  Form, Input,
} from 'antd'
import {
  DashboardOutlined, AppstoreOutlined, ReadOutlined, SwapOutlined,
  UserOutlined, LogoutOutlined, DownloadOutlined, UploadOutlined,
  EyeOutlined, EyeInvisibleOutlined, BulbOutlined, KeyOutlined, SyncOutlined,
} from '@ant-design/icons'
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Platforms from './pages/Platforms.jsx'
import PlatformDetail from './pages/PlatformDetail.jsx'
import Notes from './pages/Notes.jsx'
import Transactions from './pages/Transactions.jsx'
import Login from './pages/Login.jsx'
import {
  getStoredUser, getToken, logout, exportBackup, importBackup, changePassword,
} from './api'
import { setMask } from './constants'

const { Header, Content } = Layout
const lsBool = (k) => localStorage.getItem(k) === '1'

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null))
  const [dark, setDark] = useState(() => lsBool('dark'))
  const [privacy, setPrivacy] = useState(() => lsBool('privacy'))
  const [autoRefresh, setAutoRefresh] = useState(() => lsBool('autoRefresh'))
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  const fileRef = useRef(null)

  // 隐私模式：同步到 constants 的模块标记（fmt 据此打码）
  useEffect(() => {
    setMask(privacy)
    localStorage.setItem('privacy', privacy ? '1' : '0')
  }, [privacy])

  useEffect(() => {
    localStorage.setItem('dark', dark ? '1' : '0')
    document.body.style.background = dark ? '#000' : '#f0f2f5'
  }, [dark])

  useEffect(() => {
    localStorage.setItem('autoRefresh', autoRefresh ? '1' : '0')
  }, [autoRefresh])

  // 任何请求返回 401 时，api 拦截器会广播 auth:logout → 回到登录页
  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('auth:logout', onLogout)
    return () => window.removeEventListener('auth:logout', onLogout)
  }, [])

  const doLogout = () => {
    logout()
    setUser(null)
    navigate('/')
  }

  const doExport = async () => {
    try {
      const data = await exportBackup()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `资产备份_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      message.success('已导出备份')
    } catch (e) {
      message.error('导出失败：' + e.message)
    }
  }

  const onPickFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    let payload
    try {
      payload = JSON.parse(await file.text())
    } catch {
      message.error('文件不是有效的备份 JSON')
      return
    }
    Modal.confirm({
      title: '确认导入备份？',
      content: '导入会【覆盖】你当前账号的全部平台、资产、交易、心得，且不可撤销。建议先导出当前数据备份。',
      okText: '覆盖导入',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          const r = await importBackup(payload)
          message.success(`已导入：平台${r.platforms} 资产${r.holdings} 交易${r.transactions} 心得${r.notes}`)
          setTimeout(() => window.location.reload(), 600)
        } catch (e) {
          message.error('导入失败：' + (e.response?.data?.detail || e.message))
        }
      },
    })
  }

  const submitPwd = async () => {
    const v = await pwdForm.validateFields()
    try {
      await changePassword({ old_password: v.old_password, new_password: v.new_password })
      message.success('密码已修改')
      setPwdOpen(false)
      pwdForm.resetFields()
    } catch (e) {
      message.error('修改失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const algorithm = dark ? theme.darkAlgorithm : theme.defaultAlgorithm

  if (!user) {
    return (
      <ConfigProvider theme={{ algorithm }}>
        <Login onAuthed={setUser} />
      </ConfigProvider>
    )
  }

  const selected = location.pathname.startsWith('/platforms')
    ? '/platforms'
    : location.pathname.startsWith('/transactions')
      ? '/transactions'
      : location.pathname.startsWith('/notes')
        ? '/notes'
        : '/'

  const items = [
    { key: '/', icon: <DashboardOutlined />, label: <Link to="/">总览</Link> },
    { key: '/platforms', icon: <AppstoreOutlined />, label: <Link to="/platforms">平台管理</Link> },
    { key: '/transactions', icon: <SwapOutlined />, label: <Link to="/transactions">交易记录</Link> },
    { key: '/notes', icon: <ReadOutlined />, label: <Link to="/notes">投资心得</Link> },
  ]

  const userMenu = {
    items: [
      {
        key: 'privacy',
        icon: privacy ? <EyeInvisibleOutlined /> : <EyeOutlined />,
        label: `隐私模式：${privacy ? '开' : '关'}`,
        onClick: () => setPrivacy((v) => !v),
      },
      {
        key: 'dark',
        icon: <BulbOutlined />,
        label: `深色模式：${dark ? '开' : '关'}`,
        onClick: () => setDark((v) => !v),
      },
      {
        key: 'auto',
        icon: <SyncOutlined />,
        label: `进总览自动刷新：${autoRefresh ? '开' : '关'}`,
        onClick: () => setAutoRefresh((v) => !v),
      },
      { type: 'divider' },
      { key: 'pwd', icon: <KeyOutlined />, label: '修改密码', onClick: () => setPwdOpen(true) },
      { key: 'export', icon: <DownloadOutlined />, label: '导出备份', onClick: doExport },
      { key: 'import', icon: <UploadOutlined />, label: '导入备份', onClick: () => fileRef.current?.click() },
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: doLogout },
    ],
  }

  return (
    <ConfigProvider theme={{ algorithm }}>
      <Layout style={{ minHeight: '100vh' }}>
        <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={onPickFile} />
        <Header style={{ display: 'flex', alignItems: 'center', paddingInline: 16 }}>
          <div style={{ color: '#fff', fontWeight: 600, fontSize: 18, marginRight: 24, whiteSpace: 'nowrap' }}>
            💰 资产管理
          </div>
          <Menu theme="dark" mode="horizontal" selectedKeys={[selected]} items={items} style={{ flex: 1, minWidth: 0 }} />
          <Dropdown menu={userMenu}>
            <Space style={{ color: '#fff', cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              {user.username}
            </Space>
          </Dropdown>
        </Header>
        <Content key={privacy ? 'priv' : 'pub'} style={{ padding: '16px', maxWidth: 1100, width: '100%', margin: '0 auto' }}>
          <Routes>
            <Route path="/" element={<Dashboard autoRefresh={autoRefresh} />} />
            <Route path="/platforms" element={<Platforms />} />
            <Route path="/platforms/:id" element={<PlatformDetail />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/notes" element={<Notes />} />
          </Routes>
        </Content>
      </Layout>

      <Modal title="修改密码" open={pwdOpen} onOk={submitPwd} onCancel={() => setPwdOpen(false)} destroyOnHidden>
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: '请输入原密码' }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '至少 6 位' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm" label="确认新密码" dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator: (_, v) =>
                  !v || getFieldValue('new_password') === v
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入不一致')),
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </ConfigProvider>
  )
}
