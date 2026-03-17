import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { Monitor, Smartphone, Globe, Trash2, Shield, Loader2 } from 'lucide-react'

interface Session {
  user_id: number
  ip: string
  user_agent: string
  last_seen: string
  created_at: string
  session_key: string
}

function parseDevice(ua: string): { label: string; isMobile: boolean } {
  const lower = ua.toLowerCase()
  if (
    lower.includes('mobile') ||
    lower.includes('android') ||
    lower.includes('iphone') ||
    lower.includes('ipad')
  ) {
    return { label: 'Mobile', isMobile: true }
  }
  if (lower.includes('firefox')) return { label: 'Firefox', isMobile: false }
  if (lower.includes('edg')) return { label: 'Edge', isMobile: false }
  if (lower.includes('chrome')) return { label: 'Chrome', isMobile: false }
  if (lower.includes('safari')) return { label: 'Safari', isMobile: false }
  return { label: 'Navigateur', isMobile: false }
}

function parseOS(ua: string): string {
  const lower = ua.toLowerCase()
  if (lower.includes('windows')) return 'Windows'
  if (lower.includes('mac os') || lower.includes('macintosh')) return 'macOS'
  if (lower.includes('linux')) return 'Linux'
  if (lower.includes('android')) return 'Android'
  if (lower.includes('iphone') || lower.includes('ipad')) return 'iOS'
  return 'Inconnu'
}

export default function Sessions({ token, role }: { token: string; role?: string }) {
  const api = useApi(token)
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const [revoking, setRevoking] = useState<string | null>(null)

  const isAdmin = role === 'admin'

  useEffect(() => {
    loadSessions()
  }, [showAll])

  const loadSessions = async () => {
    setLoading(true)
    try {
      const endpoint = showAll && isAdmin ? '/sessions/all' : '/sessions/active'
      const res = await api.get(endpoint)
      setSessions(res.data.sessions || [])
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  const revokeSession = async (sessionKey: string) => {
    if (!confirm('Revoquer cette session ?')) return
    setRevoking(sessionKey)
    try {
      await api.delete(`/sessions/revoke/${encodeURIComponent(sessionKey)}`)
      setSessions((prev) => prev.filter((s) => s.session_key !== sessionKey))
    } catch {
      /* ignore */
    } finally {
      setRevoking(null)
    }
  }

  const revokeAll = async () => {
    if (!confirm('Revoquer toutes vos sessions ? Vous serez deconnecte.')) return
    try {
      await api.delete('/sessions/revoke-all')
      setSessions([])
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Sessions actives</h2>
        </div>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showAll}
                onChange={(e) => setShowAll(e.target.checked)}
                className="rounded bg-gray-800 border-gray-600"
              />
              Tous les utilisateurs
            </label>
          )}
          <button
            onClick={revokeAll}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition flex items-center gap-2"
          >
            <Trash2 size={14} />
            Revoquer toutes les sessions
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-400" size={32} />
        </div>
      ) : sessions.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center text-gray-500 text-sm">
          Aucune session active
        </div>
      ) : (
        <div className="grid gap-4">
          {sessions.map((session) => {
            const device = parseDevice(session.user_agent)
            const os = parseOS(session.user_agent)
            return (
              <div
                key={session.session_key}
                className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex items-center justify-between hover:border-gray-700 transition"
              >
                <div className="flex items-center gap-4">
                  {/* Device icon */}
                  <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center">
                    {device.isMobile ? (
                      <Smartphone size={20} className="text-blue-400" />
                    ) : (
                      <Monitor size={20} className="text-blue-400" />
                    )}
                  </div>
                  {/* Info */}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-200">
                        {device.label} — {os}
                      </span>
                      {showAll && (
                        <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">
                          User #{session.user_id}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="flex items-center gap-1 text-xs text-gray-500">
                        <Globe size={12} />
                        {session.ip}
                      </span>
                      <span className="text-xs text-gray-600">|</span>
                      <span className="text-xs text-gray-500">
                        Derniere activite :{' '}
                        {new Date(session.last_seen).toLocaleString('fr-FR')}
                      </span>
                      <span className="text-xs text-gray-600">|</span>
                      <span className="text-xs text-gray-500">
                        Cree le :{' '}
                        {new Date(session.created_at).toLocaleString('fr-FR')}
                      </span>
                    </div>
                  </div>
                </div>
                {/* Revoke button */}
                <button
                  onClick={() => revokeSession(session.session_key)}
                  disabled={revoking === session.session_key}
                  className="px-3 py-2 bg-gray-800 hover:bg-red-600/20 hover:text-red-400 rounded-lg text-sm text-gray-400 transition flex items-center gap-2 disabled:opacity-50"
                >
                  {revoking === session.session_key ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                  Revoquer
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
