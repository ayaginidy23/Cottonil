// =============================================================================
// VoiceControls.jsx - Mic button (+ language switch) and "read aloud" button
// =============================================================================
import { useState } from 'react'
import { Mic, Square, Volume2 } from 'lucide-react'
import { canListen, canSpeak, speak, useVoiceInput } from '../lib/speech.js'

// Mic button for a chat input. onText receives the recognised text.
export function MicButton({ onText, disabled }) {
  const [lang, setLang] = useState('ar-EG')
  const { listening, voiceError, start, stop } = useVoiceInput(onText)

  if (!canListen) return null                       // e.g. Firefox: hide instead of a broken button
  return (
    <>
      <button
        type="button"
        className="lang-btn"
        onClick={() => setLang((l) => (l === 'ar-EG' ? 'en-US' : 'ar-EG'))}
        title="Voice language"
        disabled={disabled || listening}
      >
        {lang === 'ar-EG' ? 'ع' : 'EN'}
      </button>
      <button
        type="button"
        className={`chat-icon-btn ${listening ? 'recording' : ''}`}
        onClick={() => (listening ? stop() : start(lang))}
        disabled={disabled}
        aria-label={listening ? 'Stop recording' : 'Voice note'}
        title={voiceError || (listening ? 'Listening… click to stop' : 'Voice note')}
      >
        {listening ? <Square size={16} /> : <Mic size={16} />}
      </button>
    </>
  )
}

// Small button under an assistant reply.
export function SpeakButton({ text }) {
  if (!canSpeak || !text) return null
  return (
    <button type="button" className="speak-btn" onClick={() => speak(text)} aria-label="Read aloud" title="Read aloud">
      <Volume2 size={13} />
    </button>
  )
}