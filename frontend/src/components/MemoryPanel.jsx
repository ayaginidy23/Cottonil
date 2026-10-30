// =============================================================================
// MemoryPanel.jsx - "New chat" button + what the assistant remembers
// -----------------------------------------------------------------------------
// New chat  : the backend summarises the current chat into long-term memory,
//             then the screen is cleared - the memory stays.
// Memory    : shows the remembered bullet points (transparency: the user can
//             see what is kept about them).
// Forget    : deletes the long-term memory.
// =============================================================================
import { useState } from 'react'
import { Brain, MessageSquarePlus, Trash2 } from 'lucide-react'

export default function MemoryPanel({ memory, onNewChat, onForget, busy, saving }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="memory-panel">
      <button type="button" className="new-chat-btn" onClick={onNewChat} disabled={busy || saving}>
        <MessageSquarePlus size={16} />
        {saving ? 'Saving memory…' : 'New chat'}
      </button>

      <button type="button" className="memory-toggle" onClick={() => setOpen((o) => !o)}>
        <Brain size={14} />
        Memory {memory ? '' : '(empty)'}
        <span className="muted small">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="memory-box">
          {memory ? (
            <>
              <div className="memory-text" dir="auto">{memory}</div>
              <button type="button" className="chip forget-btn" onClick={onForget} disabled={busy || saving}>
                <Trash2 size={12} /> Forget
              </button>
            </>
          ) : (
            <div className="muted small">
              Nothing yet. When you start a new chat, the assistant keeps the important points of
              this one (preferences, topics) and uses them next time.
            </div>
          )}
        </div>
      )}
    </div>
  )
}