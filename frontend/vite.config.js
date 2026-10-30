// =============================================================================
// vite.config.js - Vite dev server settings
// -----------------------------------------------------------------------------
// proxy: any request from the React app to /api/... is forwarded to the FastAPI
// server on port 8000. The browser only ever talks to localhost:5173, so there
// are no CORS problems and no hard-coded API URL in the code.
// Inside Docker the API is reachable as http://api:8000 (set via API_URL).
// =============================================================================
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,          // listen on all interfaces (needed inside Docker)
    port: 5173,
    proxy: {
      '/api': process.env.API_URL || 'http://localhost:8000',
    },
  },
})
