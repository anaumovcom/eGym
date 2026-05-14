import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from '@/app/app'
import '@/app/styles.css'

async function prepareMocks() {
  if (import.meta.env.DEV) {
    const { worker } = await import('@/mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  }
}

prepareMocks().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})