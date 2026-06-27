import { useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Descriptions, Divider, Drawer, Layout, Menu, Dropdown, Avatar, Space,
  Modal, Select, Tag, Typography, message, ConfigProvider, theme, Form, Input,
} from 'antd'
import {
  DashboardOutlined, AppstoreOutlined, ReadOutlined, SwapOutlined,
  UserOutlined, LogoutOutlined, DownloadOutlined, UploadOutlined,
  EyeOutlined, EyeInvisibleOutlined, BulbOutlined, SyncOutlined,
  FundOutlined, MailOutlined, QuestionCircleOutlined,
} from '@ant-design/icons'
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Platforms from './pages/Platforms.jsx'
import PlatformDetail from './pages/PlatformDetail.jsx'
import Notes from './pages/Notes.jsx'
import Research from './pages/Research.jsx'
import Transactions from './pages/Transactions.jsx'
import Login from './pages/Login.jsx'
import {
  getStoredUser, getToken, logout, exportBackup, importBackup,
  changePassword, changeEmail, resendVerification, verifyEmail, setSecurityQuestion,
} from './api'
import { setMask } from './constants'

const { Header, Content } = Layout
const { Title, Text } = Typography
const lsBool = (k) => localStorage.getItem(k) === '1'

// 与后端 SECURITY_QUESTIONS 保持一致
const SECURITY_QUESTIONS = [
  { key: 'primary_school', text: '你的小学在哪？' },
  { key: 'su_yanzu_handsome', text: '苏彦祖帅吗？' },
  { key: 'favorite_car', text: '你最喜欢的车' },
  { key: 'first_phone', text: '你的第一个手机是什么？' },
  { key: 'favorite_game', text: '你最喜欢的游戏是什么？' },
]

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null))
  const [dark, setDark] = useState(() => lsBool('dark'))
  const [privacy, setPrivacy] = useState(() => lsBool('privacy'))
  const [autoRefresh, setAutoRefresh] = useState(() => lsBool('autoRefresh'))
  const [profileOpen, setProfileOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  const [pwdLoading, setPwdLoading] = useState(false)
  const [emailForm] = Form.useForm()
  const [emailLoading, setEmailLoading] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const [sqForm] = Form.useForm()
  const [sqLoading, setSqLoading] = useState(false)
  const fileRef = useRef(null)

  const showDevEmailLink = (url, title = '本地调试链接') => {
    if (!url) return
    Modal.info({
      title,
      content: (
        <div>
          <p>当前未启用真实邮件发送，请直接打开下面的本地验证链接：</p>
          <Input.TextArea value={url} autoSize readOnly onFocus={(e) => e.target.select()} />
        </div>
      ),
      okText: '知道了',
    })
  }

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

  // 已登录时处理 /verify-email?token=... 链接
  useEffect(() => {
    if (!user) return
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    if (token && window.location.pathname.includes('verify-email')) {
      verifyEmail(token)
        .then(() => {
          message.success('邮箱验证成功！')
          const newUser = { ...user, email_verified: true }
          setUser(newUser)
          localStorage.setItem('user', JSON.stringify(newUser))
          window.history.replaceState(null, '', '/')
        })
        .catch(() => message.error('验证链接无效或已过期'))
    }
  }, [user?.id])

  const doLogout = () => {
    logout()
    setUser(null)
    navigate('/')
  }

  const doResendVerification = async () => {
    setResendLoading(true)
    try {
      const r = await resendVerification()
      message.success('验证邮件已发送，请查收邮箱')
      showDevEmailLink(r.dev_verification_url, '本地邮箱验证链接')
    } catch (e) {
      message.error(e.response?.data?.detail || '发送失败：' + e.message)
    } finally {
      setResendLoading(false)
    }
  }

  const doChangeEmail = async () => {
    const v = await emailForm.validateFields()
    setEmailLoading(true)
    try {
      const updated = await changeEmail({ new_email: v.new_email })
      const updatedUser = updated.user || updated
      const newUser = { ...user, ...updatedUser }
      setUser(newUser)
      localStorage.setItem('user', JSON.stringify(newUser))
      message.success('邮箱已更改，验证邮件已发送，请查收')
      showDevEmailLink(updated.dev_verification_url, '本地邮箱验证链接')
      emailForm.resetFields()
    } catch (e) {
      message.error('更改失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setEmailLoading(false)
    }
  }

  const doSetSecurityQuestion = async () => {
    const v = await sqForm.validateFields()
    setSqLoading(true)
    try {
      await setSecurityQuestion({
        current_password: v.current_password,
        security_question_key: v.security_question_key,
        security_answer: v.security_answer,
      })
      const sqText = SECURITY_QUESTIONS.find((q) => q.key === v.security_question_key)?.text
      const newUser = {
        ...user,
        has_security_question: true,
        security_question_key: v.security_question_key,
        security_question_text: sqText,
      }
      setUser(newUser)
      localStorage.setItem('user', JSON.stringify(newUser))
      message.success('安全问题已设置')
      sqForm.resetFields()
    } catch (e) {
      message.error('设置失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setSqLoading(false)
    }
  }

  const submitPwd = async () => {
    const v = await pwdForm.validateFields()
    setPwdLoading(true)
    try {
      await changePassword({ old_password: v.old_password, new_password: v.new_password })
      message.success('密码已修改，请重新登录')
      logout()
      setUser(null)
      setProfileOpen(false)
    } catch (e) {
      message.error('修改失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setPwdLoading(false)
    }
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
        : location.pathname.startsWith('/research')
          ? '/research'
          : '/'

  const navItems = [
    { key: '/', icon: <DashboardOutlined />, label: <Link to="/">总览</Link> },
    { key: '/platforms', icon: <AppstoreOutlined />, label: <Link to="/platforms">资产</Link> },
    { key: '/transactions', icon: <SwapOutlined />, label: <Link to="/transactions">交易</Link> },
    { key: '/research', icon: <FundOutlined />, label: <Link to="/research">投研</Link> },
    { key: '/notes', icon: <ReadOutlined />, label: <Link to="/notes">笔记</Link> },
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
      { key: 'profile', icon: <UserOutlined />, label: '个人资料', onClick: () => setProfileOpen(true) },
      { key: 'export', icon: <DownloadOutlined />, label: '导出备份', onClick: doExport },
      { key: 'import', icon: <UploadOutlined />, label: '导入备份', onClick: () => fileRef.current?.click() },
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: doLogout },
    ],
  }

  const closeProfile = () => {
    setProfileOpen(false)
    pwdForm.resetFields()
    emailForm.resetFields()
    sqForm.resetFields()
  }

  return (
    <ConfigProvider theme={{ algorithm }}>
      <Layout style={{ minHeight: '100vh' }}>
        <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={onPickFile} />

        <Header style={{ display: 'flex', alignItems: 'center', paddingInline: 16 }}>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 18, marginRight: 28, whiteSpace: 'nowrap' }}>
            TS FinancialSystem
          </div>
          <Menu theme="dark" mode="horizontal" selectedKeys={[selected]} items={navItems} style={{ flex: 1, minWidth: 0 }} />
          <Dropdown menu={userMenu}>
            <Space style={{ color: '#fff', cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              {user.username}
            </Space>
          </Dropdown>
        </Header>

        <Content key={privacy ? 'priv' : 'pub'} style={{ padding: '20px 16px', maxWidth: 1280, width: '100%', margin: '0 auto' }}>
          {/* 只在有邮箱且未验证时显示提醒 */}
          {user && user.email && !user.email_verified && (
            <Alert
              type="warning"
              showIcon
              icon={<MailOutlined />}
              style={{ marginBottom: 16 }}
              message="邮箱未验证"
              description="请查收注册时使用的邮箱，点击验证链接完成验证。验证后可使用找回密码等功能。"
              action={
                <Space direction="vertical">
                  <a
                    onClick={resendLoading ? undefined : doResendVerification}
                    style={{ cursor: resendLoading ? 'not-allowed' : 'pointer' }}
                  >
                    {resendLoading ? '发送中...' : '重新发送验证邮件'}
                  </a>
                </Space>
              }
            />
          )}
          <Routes>
            <Route path="/" element={<Dashboard autoRefresh={autoRefresh} />} />
            <Route path="/platforms" element={<Platforms />} />
            <Route path="/platforms/:id" element={<PlatformDetail />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/notes" element={<Notes />} />
            <Route path="/research" element={<Research />} />
          </Routes>
        </Content>
      </Layout>

      {/* 个人资料 Drawer */}
      <Drawer
        title="个人资料"
        open={profileOpen}
        onClose={closeProfile}
        width={440}
        destroyOnClose={false}
      >
        <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="邮箱">
            {user?.email ? (
              <Space wrap>
                <span>{user.email}</span>
                {user.email_verified
                  ? <Tag color="success">已验证</Tag>
                  : <Tag color="warning">未验证</Tag>
                }
              </Space>
            ) : (
              <Text type="secondary">未设置</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="安全问题">
            {user?.has_security_question
              ? <Tag color="success">已设置</Tag>
              : <Tag color="warning">未设置</Tag>
            }
            {user?.security_question_text && (
              <Text type="secondary" style={{ marginLeft: 8 }}>{user.security_question_text}</Text>
            )}
          </Descriptions.Item>
        </Descriptions>

        {user?.email && !user?.email_verified && (
          <div style={{ marginBottom: 8 }}>
            <Button
              type="link"
              icon={<MailOutlined />}
              loading={resendLoading}
              onClick={doResendVerification}
              style={{ padding: 0 }}
            >
              重新发送验证邮件
            </Button>
          </div>
        )}

        <Divider />
        <Title level={5} style={{ marginTop: 0 }}>
          {user?.email ? '更改邮箱' : '绑定邮箱'}
        </Title>
        <Form form={emailForm} layout="vertical">
          <Form.Item
            name="new_email"
            label="邮箱地址"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input placeholder="输入邮箱地址" autoComplete="email" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" loading={emailLoading} onClick={doChangeEmail}>
              {user?.email ? '更改邮箱' : '绑定邮箱'}
            </Button>
          </Form.Item>
        </Form>

        <Divider />
        <Title level={5} style={{ marginTop: 0 }}>
          {user?.has_security_question ? '修改安全问题' : '设置安全问题'}
        </Title>
        <Form form={sqForm} layout="vertical">
          <Form.Item
            name="current_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码以确认身份' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="security_question_key"
            label="安全问题"
            rules={[{ required: true, message: '请选择安全问题' }]}
          >
            <Select placeholder="请选择安全问题" suffixIcon={<QuestionCircleOutlined />}>
              {SECURITY_QUESTIONS.map((q) => (
                <Select.Option key={q.key} value={q.key}>{q.text}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="security_answer"
            label="答案"
            extra="请牢记此答案，找回密码时需要"
            rules={[
              { required: true, message: '请输入答案' },
              { max: 100, message: '答案最多 100 字符' },
            ]}
          >
            <Input placeholder="输入你的答案" autoComplete="off" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" loading={sqLoading} onClick={doSetSecurityQuestion}>
              {user?.has_security_question ? '修改安全问题' : '设置安全问题'}
            </Button>
          </Form.Item>
        </Form>

        <Divider />
        <Title level={5} style={{ marginTop: 0 }}>修改密码</Title>
        <Form form={pwdForm} layout="vertical">
          <Form.Item
            name="old_password"
            label="原密码"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, message: '至少 8 位' },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={['new_password']}
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
          <Form.Item>
            <Button type="primary" loading={pwdLoading} onClick={submitPwd}>
              修改密码
            </Button>
          </Form.Item>
        </Form>
      </Drawer>
    </ConfigProvider>
  )
}
