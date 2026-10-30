import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="empty page">
      <h2>Page not found</h2>
      <Link to="/apps/executive">Go to the Executive Dashboard</Link>
    </div>
  )
}
