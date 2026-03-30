import { useState, useRef, type FormEvent } from 'react'
import { askChat } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const quickQueries = [
  { label: 'Today in history', query: 'today in history' },
  { label: 'This week', query: 'this week' },
  { label: 'Total stats', query: 'total stats' },
  { label: 'Top projects', query: 'top projects' },
  { label: 'Top tags', query: 'top tags' },
  { label: 'Yesterday', query: 'yesterday' }
]

export default function Chat() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const handleSubmit = async (e?: FormEvent, query?: string) => {
    e?.preventDefault()
    const text = query || question
    if (!text.trim()) return
    
    const userMessage: Message = { role: 'user', content: text }
    setMessages(prev => [...prev, userMessage])
    setQuestion('')
    setLoading(true)
    
    try {
      const res = await askChat(text)
      const assistantMessage: Message = { role: 'assistant', content: res.answer }
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = { 
        role: 'assistant', 
        content: `Error: ${error instanceof Error ? error.message : 'Unable to get response.'}` 
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
      setTimeout(scrollToBottom, 100)
    }
  }

  return (
    <div className="container">
      <h1>Chat</h1>
      
      {messages.length > 0 && (
        <div className="chat-messages">
          {messages.map((msg, idx) => (
            <div key={idx} className={`chat-message ${msg.role}`}>
              <p>{msg.content}</p>
            </div>
          ))}
          {loading && (
            <div className="chat-message assistant">
              <div className="loading-spinner" style={{ padding: '0.5rem' }}>
                <div className="spinner" style={{ width: '20px', height: '20px' }}></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      <form onSubmit={(e) => handleSubmit(e)}>
        <input 
          type="text" 
          value={question} 
          onChange={e => setQuestion(e.target.value)} 
          placeholder="Ask a question..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          Send
        </button>
      </form>
      
      <div className="quick-actions">
        {quickQueries.map(q => (
          <button 
            key={q.label}
            onClick={() => handleSubmit(undefined, q.query)}
            disabled={loading}
          >
            {q.label}
          </button>
        ))}
      </div>
    </div>
  )
}
