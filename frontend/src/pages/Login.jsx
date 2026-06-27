import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Modal, Select, Tabs, Typography, message } from 'antd'
import { LockOutlined, MailOutlined, QuestionCircleOutlined, UserOutlined } from '@ant-design/icons'
import {
  forgotPassword, getRecoveryQuestion, login, register,
  resetPassword, resetPasswordBySecurityQuestion, verifyEmail,
} from '../api'

const { Title, Text } = Typography

// 与后端 SECURITY_QUESTIONS 保持一致
const SECURITY_QUESTIONS = [
  { key: 'primary_school', text: '你的小学在哪？' },
  { key: 'su_yanzu_handsome', text: '苏彦祖帅吗？' },
  { key: 'favorite_car', text: '你最喜欢的车' },
  { key: 'first_phone', text: '你的第一个手机是什么？' },
  { key: 'favorite_game', text: '你最喜欢的游戏是什么？' },
]

function detectMode() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  const path = window.location.pathname
  if (token && path.includes('verify-email')) return { mode: 'verify-email', token }
  if (token && path.includes('reset-password')) return { mode: 'reset-password', token }
  return { mode: null, token: null }
}

export default function Login({ onAuthed }) {
  const [tab, setTab] = useState('login')
  const [loading, setLoading] = useState(false)
  const [loginForm] = Form.useForm()
  const [regForm] = Form.useForm()

  // 安全问题找回密码状态机
  const [recoveryState, setRecoveryState] = useState(null)  // null | 'step1' | 'step2' | 'success'
  const [recoveryUsername, setRecoveryUsername] = useState('')
  const [recoveryQuestion, setRecoveryQuestion] = useState(null)  // { key, text }
  const [usernameForm] = Form.useForm()
  const [answerForm] = Form.useForm()

  // 邮箱重置密码状态（保留备用）
  const [resetState, setResetState] = useState(null)
  const [resetToken, setResetToken] = useState(null)
  const [resetForm] = Form.useForm()

  // 邮箱验证结果
  const [verifyResult, setVerifyResult] = useState(null)  // null | 'ok' | 'error'

  const showDevEmailLink = (url, title = '本地调试链接') => {
    if (!url) return
    Modal.info({
      title,
      content: (
        <div>
          <p>当前未启用真实邮件发送，请直接打开下面的本地链接：</p>
          <Input.TextArea value={url} autoSize readOnly onFocus={(e) => e.target.select()} />
        </div>
      ),
      okText: '知道了',
    })
  }

  useEffect(() => {
    const { mode, token } = detectMode()
    if (mode === 'reset-password') {
      setResetToken(token)
      setResetState('form')
    } else if (mode === 'verify-email') {
      verifyEmail(token)
        .then(() => setVerifyResult('ok'))
        .catch(() => setVerifyResult('error'))
    }
  }, [])

  const doLogin = async () => {
    const v = await loginForm.validateFields()
    setLoading(true)
    try {
      const user = await login(v)
      message.success(`欢迎回来，${user.username}`)
      onAuthed(user)
    } catch (e) {
      message.error(e.response?.data?.detail || '登录失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const doRegister = async () => {
    const v = await regForm.validateFields()
    setLoading(true)
    try {
      const user = await register(v)
      if (v.email) {
        message.success(`注册成功，欢迎 ${user.username}！请查收验证邮件`)
        showDevEmailLink(user.dev_verification_url, '本地邮箱验证链接')
      } else {
        message.success(`注册成功，欢迎 ${user.username}！`)
      }
      onAuthed(user)
    } catch (e) {
      message.error(e.response?.data?.detail || '注册失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 安全问题找回：Step 1 → 查询问题
  const doGetRecoveryQuestion = async () => {
    const v = await usernameForm.validateFields()
    setLoading(true)
    try {
      const r = await getRecoveryQuestion(v.username)
      if (r.ok) {
        setRecoveryUsername(v.username)
        setRecoveryQuestion({ key: r.question_key, text: r.question_text })
        setRecoveryState('step2')
      } else {
        message.error(r.message || '该账号无法使用安全问题找回密码，请联系管理员')
      }
    } catch (e) {
      message.error(e.response?.data?.detail || '查询失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 安全问题找回：Step 2 → 提交答案重置密码
  const doResetBySecurityQuestion = async () => {
    const v = await answerForm.validateFields()
    setLoading(true)
    try {
      await resetPasswordBySecurityQuestion({
        username: recoveryUsername,
        security_question_key: recoveryQuestion.key,
        security_answer: v.security_answer,
        new_password: v.new_password,
      })
      setRecoveryState('success')
    } catch (e) {
      message.error(e.response?.data?.detail || '安全问题答案错误或请求无效')
    } finally {
      setLoading(false)
    }
  }

  const doReset = async () => {
    const v = await resetForm.validateFields()
    setLoading(true)
    try {
      await resetPassword(resetToken, v.new_password)
      setResetState('success')
    } catch (e) {
      message.error(e.response?.data?.detail || '重置失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const resetRecovery = () => {
    setRecoveryState(null)
    setRecoveryUsername('')
    setRecoveryQuestion(null)
    usernameForm.resetFields()
    answerForm.resetFields()
  }

  // ── 邮箱验证结果页 ──────────────────────────────────────────────────
  if (verifyResult !== null) {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Title level={4} style={{ textAlign: 'center' }}>邮箱验证</Title>
          {verifyResult === 'ok'
            ? <Alert type="success" message="邮箱验证成功！" description="你可以回到登录页正常使用了。" showIcon />
            : <Alert type="error" message="验证失败" description="链接无效或已过期，请重新发送验证邮件。" showIcon />
          }
          <Button block style={{ marginTop: 16 }} onClick={() => {
            window.history.replaceState(null, '', '/')
            setVerifyResult(null)
          }}>
            返回登录
          </Button>
        </Card>
      </PageWrap>
    )
  }

  // ── 邮箱 token 重置密码（通过邮件链接进入）────────────────────────────
  if (resetState === 'form') {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Title level={4} style={{ textAlign: 'center' }}>重置密码</Title>
          <Form form={resetForm} layout="vertical">
            <Form.Item
              name="new_password"
              label="新密码"
              rules={[{ required: true, message: '请输入新密码' }, { min: 8, message: '密码至少 8 位' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少 8 位）" autoComplete="new-password" />
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
              <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" autoComplete="new-password" />
            </Form.Item>
            <Button type="primary" block loading={loading} onClick={doReset}>确认重置</Button>
          </Form>
        </Card>
      </PageWrap>
    )
  }

  if (resetState === 'success') {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Alert type="success" message="密码已重置" description="请使用新密码重新登录。" showIcon />
          <Button block style={{ marginTop: 16 }} onClick={() => {
            window.history.replaceState(null, '', '/')
            setResetState(null)
          }}>去登录</Button>
        </Card>
      </PageWrap>
    )
  }

  // ── 安全问题找回：Step 1（输入用户名）──────────────────────────────────
  if (recoveryState === 'step1') {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Title level={4} style={{ textAlign: 'center' }}>找回密码</Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
            请输入你的用户名，我们将展示你设置的安全问题。
          </Text>
          <Form form={usernameForm} layout="vertical">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
            </Form.Item>
            <Button type="primary" block loading={loading} onClick={doGetRecoveryQuestion}>下一步</Button>
            <Button block style={{ marginTop: 8 }} onClick={resetRecovery}>返回登录</Button>
          </Form>
        </Card>
      </PageWrap>
    )
  }

  // ── 安全问题找回：Step 2（回答问题+设新密码）───────────────────────────
  if (recoveryState === 'step2') {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Title level={4} style={{ textAlign: 'center' }}>找回密码</Title>
          <Alert
            type="info"
            showIcon
            icon={<QuestionCircleOutlined />}
            message={`安全问题：${recoveryQuestion?.text}`}
            style={{ marginBottom: 16 }}
          />
          <Form form={answerForm} layout="vertical">
            <Form.Item
              name="security_answer"
              label="答案"
              rules={[{ required: true, message: '请输入答案' }]}
            >
              <Input placeholder="请输入你注册时设置的答案" autoComplete="off" />
            </Form.Item>
            <Form.Item
              name="new_password"
              label="新密码"
              rules={[{ required: true, message: '请输入新密码' }, { min: 8, message: '密码至少 8 位' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少 8 位）" autoComplete="new-password" />
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
              <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" autoComplete="new-password" />
            </Form.Item>
            <Button type="primary" block loading={loading} onClick={doResetBySecurityQuestion}>重置密码</Button>
            <Button block style={{ marginTop: 8 }} onClick={() => {
              setRecoveryState('step1')
              answerForm.resetFields()
            }}>上一步</Button>
          </Form>
        </Card>
      </PageWrap>
    )
  }

  // ── 安全问题找回：成功 ──────────────────────────────────────────────
  if (recoveryState === 'success') {
    return (
      <PageWrap>
        <Card style={{ width: 380, maxWidth: '100%' }}>
          <Alert type="success" message="密码已重置" description="请使用新密码重新登录。" showIcon />
          <Button block style={{ marginTop: 16 }} onClick={resetRecovery}>去登录</Button>
        </Card>
      </PageWrap>
    )
  }

  // ── 主登录/注册页 ───────────────────────────────────────────────────
  return (
    <PageWrap>
      <Card style={{ width: 420, maxWidth: '100%' }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 8 }}>TS FinancialSystem</Title>
        <Tabs
          activeKey={tab}
          onChange={setTab}
          centered
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form form={loginForm} layout="vertical" onFinish={doLogin}>
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" onPressEnter={doLogin} />
                  </Form.Item>
                  <Button type="primary" block loading={loading} onClick={doLogin}>登录</Button>
                  <div style={{ textAlign: 'right', marginTop: 8 }}>
                    <Text
                      style={{ cursor: 'pointer', color: '#1677ff' }}
                      onClick={() => setRecoveryState('step1')}
                    >
                      忘记密码？
                    </Text>
                  </div>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form form={regForm} layout="vertical" onFinish={doRegister}>
                  <Form.Item
                    name="username"
                    rules={[
                      { required: true, message: '请输入用户名' },
                      { pattern: /^[a-zA-Z0-9_-]{3,32}$/, message: '只允许字母、数字、下划线、短横线，长度 3-32' },
                    ]}
                  >
                    <Input prefix={<UserOutlined />} placeholder="用户名（3-32位）" autoComplete="username" />
                  </Form.Item>
                  <Form.Item
                    name="email"
                    rules={[{ type: 'email', message: '邮箱格式不正确' }]}
                    extra="可选，用于邮箱验证和找回密码"
                  >
                    <Input prefix={<MailOutlined />} placeholder="邮箱（可选）" autoComplete="email" />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[
                      { required: true, message: '请设置密码' },
                      { min: 8, message: '密码至少 8 位' },
                    ]}
                  >
                    <Input.Password prefix={<LockOutlined />} placeholder="密码（至少 8 位）" autoComplete="new-password" />
                  </Form.Item>
                  <Form.Item
                    name="security_question_key"
                    label="安全问题"
                    rules={[{ required: true, message: '请选择安全问题，用于找回密码' }]}
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
                      { required: true, message: '请输入安全问题的答案' },
                      { max: 100, message: '答案最多 100 字符' },
                    ]}
                  >
                    <Input placeholder="输入安全问题的答案" autoComplete="off" />
                  </Form.Item>
                  <Button type="primary" block loading={loading} onClick={doRegister}>注册并登录</Button>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </PageWrap>
  )
}

function PageWrap({ children }) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f0f2f5',
      padding: 16,
    }}>
      {children}
    </div>
  )
}
