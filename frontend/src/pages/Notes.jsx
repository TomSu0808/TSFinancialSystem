import { useEffect, useState } from 'react'
import {
  Button, Card, Col, Empty, Form, Input, Modal, Popconfirm, Row, Space, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { listNotes, createNote, updateNote, deleteNote } from '../api'

const fmtDate = (s) => {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function Notes() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      setData(await listNotes())
    } catch (e) {
      message.error('加载心得失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    setOpen(true)
  }
  const openEdit = (record) => {
    setEditing(record)
    form.setFieldsValue(record)
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) await updateNote(editing.id, values)
      else await createNote(values)
      message.success('已保存')
      setOpen(false)
      load()
    } catch (e) {
      message.error('保存失败：' + e.message)
    }
  }

  const remove = async (id) => {
    try {
      await deleteNote(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error('删除失败：' + e.message)
    }
  }

  return (
    <Card
      title="投资心得"
      loading={loading}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
          新增
        </Button>
      }
    >
      {data.length === 0 ? (
        <Empty description="还没有心得，点右上角「新增」记下你的第一条投资语录 / 笔记" />
      ) : (
        <Row gutter={[16, 16]}>
          {data.map((note) => (
            <Col xs={24} sm={12} key={note.id}>
              <Card
                size="small"
                title={note.title || '（无标题）'}
                styles={{ body: { whiteSpace: 'pre-wrap', minHeight: 80 } }}
                extra={
                  <Space size="small">
                    <a onClick={() => openEdit(note)}>编辑</a>
                    <Popconfirm title="删除这条心得？" onConfirm={() => remove(note.id)}>
                      <a style={{ color: '#cf1322' }}>删除</a>
                    </Popconfirm>
                  </Space>
                }
              >
                <div>{note.content}</div>
                <div style={{ marginTop: 12, color: '#aaa', fontSize: 12, textAlign: 'right' }}>
                  {fmtDate(note.created_at)}
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title={editing ? '编辑心得' : '新增心得'}
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题（可选）">
            <Input placeholder="如：巴菲特语录、定投纪律…" />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '写点什么吧' }]}>
            <Input.TextArea rows={8} placeholder="自由记录投资语录、笔记、复盘想法…" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
