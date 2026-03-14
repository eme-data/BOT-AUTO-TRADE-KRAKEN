import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { HeartPulse, RefreshCw, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'

interface LoopStatus { [name: string]: string }
interface ContextHealth {
  user_id: number
  running: boolean
  uptime_seconds: number
  last_tick_at: string | null
  active_pairs: string[]
  active_pairs_count: number
  mode: string
  loops_status: LoopStatus
}
interface HealthData {
  ok: boolean
  memory: { rss_mb: number; vms_mb: number } | null
  data: {
    checked_at: string | null
    contexts: Record<string, ContextHealth>
  } | null
  error?: string
}

function formatUptime(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return `${h}h ${m}m`
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'alive') return <CheckCircle2 size={14} className="text-green-400" />
  if (status === 'dead') return <XCircle size={14} className="text-red-400" />
  return <AlertCircle size={14} className="text-yellow-400" />
}

export default function Health({ token }: { token: string }) {
  const api = useApi(token)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/bot/health')
      setHealth(res.data)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  // Auto-refresh every 30s
  useEffect(() => {
    const iv = setInterval(load, 30000)
    return () => clearInterval(iv)
  }, [])

  const contexts = health?.data?.contexts ? Object.values(health.data.contexts) : []

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <HeartPulse size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Health Dashboard</h2>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Rafraichir
        </button>
      </div>

      {loading && !health && (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-400" size={32} />
        </div>
      )}

      {health && (
        <div className="space-y-6">
          {/* Global status */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-xs text-gray-500 mb-1">Statut global</p>
              <p className={`text-lg font-bold ${health.ok ? 'text-green-400' : 'text-red-400'}`}>
                {health.ok ? 'OK' : 'Erreur'}
              </p>
            </div>
            {health.memory && (
              <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                <p className="text-xs text-gray-500 mb-1">Memoire RSS</p>
                <p className="text-lg font-bold">{health.memory.rss_mb} MB</p>
              </div>
            )}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-xs text-gray-500 mb-1">Contextes actifs</p>
              <p className="text-lg font-bold">{contexts.length}</p>
            </div>
          </div>

          {health.data?.checked_at && (
            <p className="text-xs text-gray-500">
              Dernier check : {new Date(health.data.checked_at).toLocaleString('fr-FR')}
            </p>
          )}

          {/* Contexts */}
          {contexts.map(ctx => (
            <div key={ctx.user_id} className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className={`w-3 h-3 rounded-full ${ctx.running ? 'bg-green-500' : 'bg-red-500'}`} />
                  <h3 className="font-semibold">User #{ctx.user_id}</h3>
                  <span className={`px-2 py-0.5 rounded text-xs ${ctx.mode === 'PAPER' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}`}>
                    {ctx.mode}
                  </span>
                </div>
                <span className="text-sm text-gray-400">Uptime: {formatUptime(ctx.uptime_seconds)}</span>
              </div>

              {/* Loops status */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                {Object.entries(ctx.loops_status).map(([name, status]) => (
                  <div key={name} className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                    <StatusIcon status={status} />
                    <span className="text-xs text-gray-300">{name}</span>
                  </div>
                ))}
              </div>

              {/* Pairs */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-gray-500">Paires actives:</span>
                {ctx.active_pairs.map(p => (
                  <span key={p} className="text-xs bg-gray-800 px-2 py-0.5 rounded text-gray-300">{p}</span>
                ))}
                {ctx.active_pairs.length === 0 && (
                  <span className="text-xs text-gray-600">Aucune</span>
                )}
              </div>

              {ctx.last_tick_at && (
                <p className="text-xs text-gray-500 mt-2">
                  Dernier tick: {new Date(ctx.last_tick_at).toLocaleString('fr-FR')}
                </p>
              )}
            </div>
          ))}

          {contexts.length === 0 && !loading && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
              <HeartPulse size={48} className="text-gray-700 mx-auto mb-4" />
              <p className="text-gray-500">Aucun contexte actif</p>
              <p className="text-gray-600 text-sm mt-1">Le bot n'a pas encore demarre ou les donnees ne sont pas disponibles</p>
            </div>
          )}

          {health.error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
              {health.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
