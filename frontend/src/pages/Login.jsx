import { useState } from 'react'
import { Button, Card, Form, Input, Tabs, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { login, register } from '../api'

const { Title } = Typography

export default function Login({ onAuthed }) {
  const [tab, setTab] = useState('login')
  const [loading, setLoading] = useState(false)
  const [loginForm] = Form.useForm()
  const [regForm] = Form.useForm()

  const doLogin = async () => {
    const v = await loginForm.validateFields()
    setLoading(true)
    try {
      const user = await login(v)
      message.success(`欢迎回来，${user.username}`)
      onAuthed(user)
    } catch (e) {
      message.error(e.response?.data?.detail || ('登录失败：' + e.message))
    } finally {
      setLoading(false)
    }
  }

  const doRegister = async () => {
    const v = await regForm.validateFields()
    setLoading(true)
    try {
      const user = await register(v)
      message.success(`注册成功，欢迎 ${user.username}`)
      onAuthed(user)
    } catch (e) {
      message.error(e.response?.data?.detail || ('注册失败：' + e.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5', padding: 16 }}>
      <Card style={{ width: 380, maxWidth: '100%' }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 8 }}>💰 资产管理</Title>
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
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form form={regForm} layout="vertical" onFinish={doRegister}>
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
                  </Form.Item>
                  <Form.Item name="email" rules={[{ type: 'email', message: '邮箱格式不正确' }]} extra="可选，用于将来找回密码">
                    <Input prefix={<MailOutlined />} placeholder="邮箱（可选）" autoComplete="email" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请设置密码' }, { min: 6, message: '密码至少 6 位' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="设置密码" autoComplete="new-password" />
                  </Form.Item>
                  <Button type="primary" block loading={loading} onClick={doRegister}>注册并登录</Button>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
