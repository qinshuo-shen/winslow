import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// Web Push (focus-timer session notifications, see components/FocusTimer/
// usePushSubscription.ts) -- registered unconditionally at app load, before
// any permission prompt, so the service worker is ready by the time the
// user opts in later. Best-effort: an unsupported browser or a failed
// registration shouldn't block the app from loading.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
