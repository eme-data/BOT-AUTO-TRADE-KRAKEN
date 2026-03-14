import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import axios from 'axios'
import Login from './pages/Login'
import Setup from './pages/Setup'
import Dashboard from './pages/Dashboard'
import Trades from './pages/Trades'
import Settings from './pages/Settings'
import AIAnalysis from './pages/AIAnalysis'
import BotLogs from './pages/BotLogs'
import Layout from './components/Layout'

export default function App() {
  const [token, setToken] = useState<string | null>(
    localStorage.getItem('token'),
  )
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [checkingConfig, setCheckingConfig] = useState(true)

  useEffect(() => {
    if (token) localStorage.setItem('token', token)
    else localStorage.removeItem('token')
  }, [token])

  // Check if Kraken credentials are configured
  useEffect(() => {
    if (!token) {
      setCheckingConfig(false)
      return
    }
    const check = async () => {
      try {
        const res = await axios.get('/api/settings/status', {
          headers: { Authorization: `Bearer ${token}` },
        })
        setConfigured(res.data.configured)
      } catch {
        setConfigured(false)
      } finally {
        setCheckingConfig(false)
      }
    }
    check()
  }, [token])

  if (!token) {
    return <Login onLogin={setToken} />
  }

  if (checkingConfig) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <p className="text-gray-400">Chargement...</p>
      </div>
    )
  }

  // Show setup wizard if not yet configured
  if (configured === false) {
    return (
      <Setup
        token={token}
        onComplete={() => setConfigured(true)}
      />
    )
  }

  return (
    <Layout onLogout={() => setToken(null)}>
      <Routes>
        <Route path="/" element={<Dashboard token={token} />} />
        <Route path="/trades" element={<Trades token={token} />} />
        <Route path="/settings" element={<Settings token={token} />} />
        <Route path="/ai" element={<AIAnalysis token={token} />} />
        <Route path="/logs" element={<BotLogs token={token} />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}
