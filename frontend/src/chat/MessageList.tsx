import type { Citations } from '../api/types'
import { CitationPanel } from './CitationPanel'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: Citations | null
}

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="message-list">
      {messages.map((m, i) => (
        <div key={i} className={`message message-${m.role}`}>
          <div className="message-bubble">{m.content}</div>
          {m.role === 'assistant' && <CitationPanel citations={m.citations} />}
        </div>
      ))}
    </div>
  )
}
