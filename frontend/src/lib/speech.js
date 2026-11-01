// =============================================================================
// speech.js - Voice notes (speech -> text) and "read aloud" (text -> speech)
// -----------------------------------------------------------------------------
// Uses the browser's built-in Web Speech API: no API key, no server, free.
//   SpeechRecognition : microphone -> text (best in Chrome / Edge)
//   speechSynthesis   : text -> voice (all modern browsers)
// The recognised text is put in the input box, so the user can check it before
// sending, and the chatbot receives normal text like a typed message.
// =============================================================================
import { useEffect, useRef, useState } from 'react'

const Recognition = typeof window !== 'undefined'
  ? window.SpeechRecognition || window.webkitSpeechRecognition
  : null

export const canListen = Boolean(Recognition)
export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

// lang: 'ar-EG' (Egyptian Arabic) or 'en-US'
// onEnd(text) is called when the user stops talking (used by the analyst's talk mode)
export function useVoiceInput(onText, onEnd) {
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState(null)
  const recRef = useRef(null)
  const activeRef = useRef(false)                        // a ref, so callbacks never see an old value
  const cb = useRef({ onText, onEnd })
  cb.current = { onText, onEnd }

  useEffect(() => () => recRef.current?.abort(), [])     // stop the mic when leaving the page

  const start = (lang = 'ar-EG') => {
    if (!Recognition || activeRef.current) return
    const rec = new Recognition()
    let heard = ''
    rec.lang = lang
    rec.interimResults = true          // show words while the user is still speaking
    rec.continuous = false             // stop automatically after a pause
    rec.onresult = (e) => {
      heard = Array.from(e.results).map((r) => r[0].transcript).join(' ')
      cb.current.onText?.(heard)
    }
    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return
      setVoiceError(e.error === 'not-allowed' ? 'Microphone permission was denied.' : `Voice error: ${e.error}`)
    }
    rec.onend = () => {
      activeRef.current = false
      setListening(false)
      cb.current.onEnd?.(heard)
    }
    recRef.current = rec
    setVoiceError(null)
    activeRef.current = true
    setListening(true)
    rec.start()
  }

  const stop = () => recRef.current?.stop()

  return { listening, voiceError, start, stop }
}

const hasArabic = (text) => /[؀-ۿ]/.test(text)

// Read a reply aloud; picks an Arabic or English voice from the text itself.
// onDone runs when the voice has finished (talk mode then listens again).
export function speak(text, onDone) {
  if (!canSpeak || !text) { onDone?.(); return }
  window.speechSynthesis.cancel()                         // stop anything already playing
  const clean = text.replace(/[*#`_>|]/g, ' ')            // don't read markdown symbols
  const u = new SpeechSynthesisUtterance(clean)
  u.lang = hasArabic(text) ? 'ar-EG' : 'en-US'
  const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith(u.lang.slice(0, 2)))
  if (voice) u.voice = voice
  u.rate = 1
  if (onDone) { u.onend = onDone; u.onerror = onDone }
  window.speechSynthesis.speak(u)
}

export function stopSpeaking() {
  if (canSpeak) window.speechSynthesis.cancel()
}
