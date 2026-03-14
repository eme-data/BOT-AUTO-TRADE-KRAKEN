import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Brain,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Send,
  Clock,
  TrendingUp,
  BarChart3,
} from 'lucide-react'

interface AILog {
  id: number
  pair: string
  mode: string
  verdict: string
  confidence: number
  reasoning: string
  market_summary: string
  risk_warnings: string[]
  suggested_adjustments: Record<string, unknown>
  signal_direction: string
  signal_strategy: string
  model_used: string
  latency_ms: number
  created_at: string
}

interface AIStats {
  total: number
  approvals: number
  rejections: number
  adjustments: number
  avg_latency_ms: number
  avg_confidence: number
}

interface AIStatus {
  enabled: boolean
  configured: boolean
  model: string
  modes: Record<string, boolean>
}

const VERDICT_STYLES: Record<string, { icon: React.ReactNode; bg: string; text: string }> = {
  APPROVE: {
    icon: <CheckCircle size={16} />,
    bg: 'bg-green-500/10',
    text: 'text-green-400',
  },
  REJECT: {
    icon: <XCircle size={16} />,
    bg: 'bg-red-500/10',
    text: 'text-red-400',
  },
  ADJUST: {
    icon: <AlertTriangle size={16} />,
    bg: 'bg-yellow-500/10',
    text: 'text-yellow-400',
  },
  INSUFFICIENT: {
    icon: <AlertTriangle size={16} />,
    bg: 'bg-gray-500/10',
    text: 'text-gray-400',
  },
}

const MODE_LABELS: Record<string, string> = {
  pre_trade: 'Pre-trade',
  market_review: 'Revue marche',
  sentiment: 'Sentiment',
  post_trade: 'Post-trade',
}

export default function AIAnalysis({ token }: { token: string }) {
  const api = useApi(token)
  const [status, setStatus] = useState<AIStatus | null>(null)
  const [stats, setStats] = useState<AIStats | null>(null)
  const [logs, setLogs] = useState<AILog[]>([])
  const [loading, setLoading] = useState(true)

  // Manual analysis
  const [analysisPair, setAnalysisPair] = useState('BTC/USD')
  const [analysisMode, setAnalysisMode] = useState('market_review')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    loadData()
  }, [token])

  const loadData = async () => {
    try {
      const [statusRes, statsRes, logsRes] = await Promise.all([
        api.get('/ai/status'),
        api.get('/ai/stats'),
        api.get('/ai/logs?limit=30'),
      ])
      setStatus(statusRes.data)
      setStats(statsRes.data)
      setLogs(logsRes.data)
    } catch {
      // AI might not be configured
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async () => {
    setAnalyzing(true)
    setAnalysisResult(null)
    try {
      const res = await api.post('/ai/analyze', {
        pair: analysisPair,
        mode: analysisMode,
      })
      setAnalysisResult(res.data)
      // Refresh logs
      const logsRes = await api.get('/ai/logs?limit=30')
      setLogs(logsRes.data)
    } catch {
      setAnalysisResult({ error: 'Erreur lors de l\'analyse' })
    } finally {
      setAnalyzing(false)
    }
  }

  if (loading) return <p className="text-gray-400">Chargement...</p>

  if (!status?.configured) {
    return (
      <div>
        <h2 className="text-2xl font-bold mb-6">Analyse IA</h2>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center">
          <Brain size={48} className="text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">IA non configuree</h3>
          <p className="text-gray-500 text-sm mb-4">
            Activez l'analyse IA et renseignez votre cle API Claude dans les parametres.
          </p>
          <a
            href="/settings"
            className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition"
          >
            Configurer
          </a>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <Brain size={24} className="text-purple-400" />
          Analyse IA
        </h2>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 rounded text-xs font-medium ${
              status?.enabled
                ? 'bg-green-500/20 text-green-400'
                : 'bg-gray-700 text-gray-400'
            }`}
          >
            {status?.enabled ? 'Active' : 'Desactive'}
          </span>
          <span className="text-xs text-gray-500">{status?.model}</span>
        </div>
      </div>

      {/* Stats cards */}
      {stats && stats.total > 0 && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<BarChart3 size={18} />}
            label="Analyses"
            value={String(stats.total)}
            color="blue"
          />
          <StatCard
            icon={<CheckCircle size={18} />}
            label="Approuvees"
            value={`${stats.approvals} (${stats.total ? Math.round((stats.approvals / stats.total) * 100) : 0}%)`}
            color="green"
          />
          <StatCard
            icon={<XCircle size={18} />}
            label="Rejetees"
            value={String(stats.rejections)}
            color="red"
          />
          <StatCard
            icon={<Clock size={18} />}
            label="Latence moy."
            value={`${stats.avg_latency_ms}ms`}
            color="purple"
          />
        </div>
      )}

      {/* Active modes */}
      {status?.modes && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 mb-6">
          <p className="text-sm text-gray-400 mb-2">Modes actifs :</p>
          <div className="flex gap-2">
            {Object.entries(status.modes).map(([mode, enabled]) => (
              <span
                key={mode}
                className={`px-3 py-1 rounded-full text-xs font-medium ${
                  enabled
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'bg-gray-800 text-gray-600'
                }`}
              >
                {MODE_LABELS[mode] || mode}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Manual analysis */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Analyse manuelle</h3>
        <div className="flex gap-3 mb-4">
          <select
            value={analysisPair}
            onChange={(e) => setAnalysisPair(e.target.value)}
            className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
          >
            {['BTC/USD', 'ETH/USD', 'SOL/USD', 'ADA/USD', 'DOT/USD', 'AVAX/USD', 'LINK/USD', 'XRP/USD'].map(
              (p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ),
            )}
          </select>
          <select
            value={analysisMode}
            onChange={(e) => setAnalysisMode(e.target.value)}
            className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="market_review">Revue de marche</option>
            <option value="sentiment">Analyse de sentiment</option>
          </select>
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            {analyzing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            Analyser
          </button>
        </div>

        {/* Analysis result */}
        {analysisResult && !('error' in analysisResult) && (
          <div className="bg-gray-800/50 rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-2">
              {VERDICT_STYLES[analysisResult.verdict as string]?.icon}
              <span
                className={`font-semibold ${
                  VERDICT_STYLES[analysisResult.verdict as string]?.text || ''
                }`}
              >
                {analysisResult.verdict as string}
              </span>
              <span className="text-gray-500 text-sm ml-2">
                Confiance: {((analysisResult.confidence as number) * 100).toFixed(0)}%
              </span>
              <span className="text-gray-600 text-xs ml-auto">
                {analysisResult.latency_ms as number}ms
              </span>
            </div>
            <p className="text-sm text-gray-300">
              {analysisResult.reasoning as string}
            </p>
            {analysisResult.market_summary && (
              <p className="text-xs text-gray-500 italic">
                {analysisResult.market_summary as string}
              </p>
            )}
            {(analysisResult.risk_warnings as string[])?.length > 0 && (
              <div className="text-xs text-yellow-400 space-y-0.5">
                {(analysisResult.risk_warnings as string[]).map((w, i) => (
                  <p key={i}>⚠ {w}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {analysisResult && 'error' in analysisResult && (
          <div className="bg-red-500/10 text-red-400 rounded-lg p-3 text-sm">
            {analysisResult.error as string}
          </div>
        )}
      </div>

      {/* Analysis log history */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800">
          <h3 className="font-semibold">Historique des analyses</h3>
        </div>
        <div className="divide-y divide-gray-800/50">
          {logs.length === 0 ? (
            <p className="px-6 py-8 text-center text-gray-500 text-sm">
              Aucune analyse effectuee
            </p>
          ) : (
            logs.map((log) => {
              const style = VERDICT_STYLES[log.verdict] || VERDICT_STYLES.INSUFFICIENT
              return (
                <div key={log.id} className="px-6 py-3 hover:bg-gray-800/30">
                  <div className="flex items-center gap-3 mb-1">
                    <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${style.bg} ${style.text}`}>
                      {style.icon}
                      {log.verdict}
                    </span>
                    <span className="font-mono text-sm">{log.pair}</span>
                    <span className="text-xs text-gray-500 px-2 py-0.5 bg-gray-800 rounded">
                      {MODE_LABELS[log.mode] || log.mode}
                    </span>
                    {log.signal_direction && (
                      <span
                        className={`text-xs ${
                          log.signal_direction === 'buy'
                            ? 'text-green-400'
                            : 'text-red-400'
                        }`}
                      >
                        {log.signal_direction.toUpperCase()}
                      </span>
                    )}
                    <span className="text-xs text-gray-600 ml-auto">
                      {log.latency_ms}ms · {new Date(log.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-400 line-clamp-2">
                    {log.reasoning}
                  </p>
                  {log.risk_warnings?.length > 0 && (
                    <div className="flex gap-2 mt-1">
                      {log.risk_warnings.map((w, i) => (
                        <span
                          key={i}
                          className="text-xs text-yellow-500/70 bg-yellow-500/5 px-2 py-0.5 rounded"
                        >
                          {w}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode
  label: string
  value: string
  color: string
}) {
  const colors: Record<string, string> = {
    blue: 'text-blue-400 bg-blue-500/10',
    green: 'text-green-400 bg-green-500/10',
    red: 'text-red-400 bg-red-500/10',
    purple: 'text-purple-400 bg-purple-500/10',
  }
  const cls = colors[color] || colors.blue

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className={`inline-flex p-2 rounded-lg ${cls} mb-2`}>{icon}</div>
      <p className="text-gray-500 text-xs mb-1">{label}</p>
      <p className="text-lg font-bold">{value}</p>
    </div>
  )
}
