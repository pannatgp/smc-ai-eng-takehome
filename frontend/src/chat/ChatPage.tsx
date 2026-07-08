import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getChatHistory, sendChatMessage } from '../api/client'
import { MessageList, type ChatMessage } from './MessageList'
import { MessageInput } from './MessageInput'

export function ChatPage() {
  const { token, logout } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!token) return
    getChatHistory(token)
      .then((history) =>
        setMessages(history.map((m) => ({ role: m.role, content: m.content, citations: m.citations }))),
      )
      .catch(() => setError('Could not load chat history'))
  }, [token])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(message: string) {
    if (!token) return
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: message }])
    setBusy(true)
    try {
      const response = await sendChatMessage(token, message)
      setMessages((prev) => [...prev, { role: 'assistant', content: response.answer, citations: response.citations }])
    } catch {
      setError('Failed to get a response. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-page">
      <header className="chat-header">
        <h1>Financial Q&amp;A Chatbot</h1>
        <button onClick={logout}>Sign out</button>
      </header>

      <MessageList messages={messages} />
      {busy && <div className="message message-assistant typing">Thinking…</div>}
      <div ref={bottomRef} />

      {error && <div className="chat-error">{error}</div>}
      <MessageInput onSend={handleSend} disabled={busy} />
    </div>
  )
}
