import { useEffect, useMemo, useRef, useState } from 'react'
import { aiChat, newChatSessionId } from '../api'
import { useUserId } from './Layout'

function nowId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export default function ChatWidget() {
  const userId = useUserId()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [messages, setMessages] = useState(() => [
    {
      id: nowId(),
      role: 'assistant',
      text: 'Chào bạn, mình là trợ lý ElecShop. Bạn cần tư vấn sản phẩm gì?',
    },
  ])

  const endRef = useRef(null)
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }), 50)
    return () => clearTimeout(t)
  }, [open, messages.length])

  const title = useMemo(() => (userId ? `AI Advisor • ${userId}` : 'AI Advisor'), [userId])

  function onNewChat() {
    newChatSessionId()
    setError('')
    setInput('')
    setMessages([
      {
        id: nowId(),
        role: 'assistant',
        text: 'Chào bạn, mình là trợ lý ElecShop. Bạn cần tư vấn sản phẩm gì?',
      },
    ])
  }

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setError('')
    const userMsg = { id: nowId(), role: 'user', text }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)
    try {
      const res = await aiChat(userId, text)
      const answer = res?.answer || 'Xin lỗi, mình chưa trả lời được lúc này.'
      setMessages((prev) => [...prev, { id: nowId(), role: 'assistant', text: answer }])
    } catch (e) {
      setError(e?.message || 'Chat failed')
      setMessages((prev) => [
        ...prev,
        {
          id: nowId(),
          role: 'assistant',
          text: 'Xin lỗi, hệ thống đang bận hoặc gặp lỗi. Bạn thử lại sau nhé.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="chatDock" aria-live="polite">
      {!open ? (
        <button className="chatFab" type="button" onClick={() => setOpen(true)} aria-label="Open chat">
          Chat
        </button>
      ) : null}

      {open ? (
        <div className="chatPanel" role="dialog" aria-label="ElecShop assistant">
          <div className="chatHeader">
            <div className="chatTitle">{title}</div>
            <button className="chatClose" type="button" onClick={onNewChat} aria-label="New chat">
              New
            </button>
            <button className="chatClose" type="button" onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </div>

          <div className="chatBody">
            {messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'chatMsg chatMsgUser' : 'chatMsg chatMsgBot'}>
                <div className="chatBubble">{m.text}</div>
              </div>
            ))}
            {loading ? (
              <div className="chatMsg chatMsgBot">
                <div className="chatBubble chatBubbleMuted">Đang trả lời...</div>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>

          <div className="chatFooter">
            {error ? <div className="chatError">{error}</div> : null}
            <div className="chatInputRow">
              <textarea
                className="chatInput"
                value={input}
                placeholder="Nhập câu hỏi..."
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                disabled={loading}
              />
              <button className="chatSend" type="button" onClick={onSend} disabled={loading || !input.trim()}>
                Gửi
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

