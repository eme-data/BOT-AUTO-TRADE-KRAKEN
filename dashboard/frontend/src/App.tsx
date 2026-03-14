import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import Login from './pages/Login'
import Setup from './pages/Setup'
import Dashboard from './pages/Dashboard'
import Trades from './pages/Trades'
import Settings from './pages/Settings'
import AIAnalysis from './pages/AIAnalysis'
import BotLogs from './pages/BotLogs'
import UsersPage from './pages/Users'
import Analytics from './pages/Analytics'
import Journal from './pages/Journal'
import AuditLog from './pages/AuditLog'
import Health from './pages/Health'
import Strategies from './pages/Strategies'
import StrategyComparison from './pages/StrategyComparison'
import Layout from './components/Layout'

function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}

export interface UserInfo {
  username: string
  role: string
  user_id: number
}

export default function App() {
  const [token, setToken] = useState<string | null>(
    localStorage.getItem('token'),
  )
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [checkingConfig, setCheckingConfig] = useState(true)

  const userInfo = useMemo<UserInfo | null>(() => {
    if (!token) return null
    const payload = decodeJwt(token)
    if (!payload) return null
    return {
      username: (payload.sub as string) || '',
      role: (payload.role as string) || 'viewer',
      user_id: (payload.user_id as number) || 0,
    }
  }, [token])

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
    <Layout onLogout={() => setToken(null)} userInfo={userInfo}>
      <Routes>
        <Route path="/" element={<Dashboard token={token} />} />
        <Route path="/trades" element={<Trades token={token} />} />
        <Route path="/analytics" element={<Analytics token={token} />} />
        <Route path="/compare" element={<StrategyComparison token={token} />} />
        <Route path="/journal" element={<Journal token={token} />} />
        <Route path="/strategies" element={<Strategies token={token} />} />
        <Route path="/settings" element={<Settings token={token} />} />
        <Route path="/ai" element={<AIAnalysis token={token} />} />
        <Route path="/logs" element={<BotLogs token={token} />} />
        <Route path="/health" element={<Health token={token} />} />
        {userInfo?.role === 'admin' && (
          <>
            <Route path="/users" element={<UsersPage token={token} />} />
            <Route path="/audit" element={<AuditLog token={token} />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}
