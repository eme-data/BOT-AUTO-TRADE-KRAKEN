import { useState } from 'react'
import axios from 'axios'
import AltiorLogo from '../assets/AltiorLogo'
import { ShieldCheck } from 'lucide-react'

interface LoginProps {
  onLogin: (token: string) => void
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const payload: Record<string, string> = { username, password }
      if (needsTotp && totpCode) {
        payload.totp_code = totpCode
      }
      const res = await axios.post('/api/auth/login', payload)

      // Check if 2FA is required
      if (res.data.requires_totp) {
        setNeedsTotp(true)
        return
      }

      onLogin(res.data.access_token)
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Invalid credentials'
      setError(detail)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 p-8 rounded-2xl shadow-xl w-96 border border-gray-800"
      >
        <div className="flex justify-center mb-6">
          <AltiorLogo size={64} className="text-blue-400" />
        </div>

        {error && (
          <p className="text-red-400 text-sm text-center mb-4">{error}</p>
        )}

        {!needsTotp ? (
          <>
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full mb-3 px-4 py-2 bg-gray-800 rounded-lg border border-gray-700 text-gray-100 focus:border-blue-500 focus:outline-none"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full mb-6 px-4 py-2 bg-gray-800 rounded-lg border border-gray-700 text-gray-100 focus:border-blue-500 focus:outline-none"
            />
          </>
        ) : (
          <div className="mb-6">
            <div className="flex items-center justify-center gap-2 mb-4">
              <ShieldCheck size={20} className="text-blue-400" />
              <p className="text-sm text-gray-300">Verification 2FA requise</p>
            </div>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="Code a 6 chiffres"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              maxLength={6}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg border border-gray-700 text-gray-100 text-center text-xl tracking-widest focus:border-blue-500 focus:outline-none"
              autoFocus
            />
            <button
              type="button"
              onClick={() => { setNeedsTotp(false); setTotpCode(''); setError('') }}
              className="w-full mt-3 text-xs text-gray-500 hover:text-gray-300 transition"
            >
              Retour
            </button>
          </div>
        )}

        <button
          type="submit"
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition"
        >
          {needsTotp ? 'Verifier' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
