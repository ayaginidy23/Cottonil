// =============================================================================
// ErrorBoundary.jsx - If a page crashes while drawing, show the error on screen
// -----------------------------------------------------------------------------
// Without this, one JavaScript error inside a page makes React remove the whole
// screen (a blank white page). With it, only that page shows a red box with the
// error message, and the sidebar keeps working.
// =============================================================================
import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Page crashed:', error, info?.componentStack)
  }

  componentDidUpdate(prev) {
    // moving to another page clears the error
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-box">
          <strong>This page crashed</strong>
          <code>{String(this.state.error?.message || this.state.error)}</code>
          <div className="muted small">Open DevTools (F12) - Console for the full details.</div>
        </div>
      )
    }
    return this.props.children
  }
}