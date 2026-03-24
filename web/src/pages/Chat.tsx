import { useState, type FormEvent } from 'react'
import { askChat } from '../lib/api'

export default function Chat() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    try {
      const res = await askChat(question)
      setAnswer(res.answer)
    } catch (error) {
      setAnswer(`Error: ${error instanceof Error ? error.message : 'Unable to load chat response.'}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h1>Chat</h1>
      <form onSubmit={handleSubmit}>
        <input 
          type="text" 
          value={question} 
          onChange={e => setQuestion(e.target.value)} 
          placeholder="Ask a question..."
        />
        <button type="submit" disabled={loading}>Send</button>
      </form>
      {loading && <p>Loading...</p>}
      {answer && (
        <div className="answer">
          <p>{answer}</p>
        </div>
      )}
    </div>
  )
}
