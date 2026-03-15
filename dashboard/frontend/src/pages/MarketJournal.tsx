import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  BookOpen,
  Loader2,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  Calendar,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

interface JournalEntry {
  id: number
  date: string
  summary: string
  sentiment: string | null
  key_events: string[] | null
  market_data: Record<string, { last: number; bid: number; ask: number; volume: number }> | null
  model_used: string | null
}

const SENTIMENT_STYLES: Record<string, { label: string; bg: string; text: string; icon: React.ReactNode }> = {
  bullish: {
    label: 'Bullish',
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    icon: <TrendingUp size={14} />,
  },
  bearish: {
    label: 'Bearish',
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    icon: <TrendingDown size={14} />,
  },
  neutral: {
    label: 'Neutral',
    bg: 'bg-gray-500/15',
    text: 'text-gray-400',
    icon: <Minus size={14} />,
  },
}

export default function MarketJournal({ token }: { token: string }) {
  const api = useApi(token)
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  useEffect(() => {
    loadEntries()
  }, [token])

  const loadEntries = async () => {
    try {
      const res = await api.get('/market-journal/?limit=30')
      setEntries(res.data)
    } catch {
      // No entries yet
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await api.post('/market-journal/generate')
      if (res.data.error) {
        setError(res.data.error)
      } else {
        // Refresh list
        const listRes = await api.get('/market-journal/?limit=30')
        setEntries(listRes.data)
      }
    } catch {
      setError("Erreur lors de la generation du journal")
    } finally {
      setGenerating(false)
    }
  }

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('fr-FR', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }

  if (loading) return <p className="text-gray-400">Chargement...</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <BookOpen size={24} className="text-blue-400" />
          Journal de Marche IA
        </h2>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          {generating ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Sparkles size={16} />
          )}
          {generating ? 'Generation en cours...' : 'Generer le journal du jour'}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl p-4 mb-6 text-sm">
          {error}
        </div>
      )}

      {generating && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 mb-6 text-center">
          <Loader2 size={32} className="animate-spin text-blue-400 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">
            L'IA analyse le marche et genere le journal du jour...
          </p>
          <p className="text-gray-600 text-xs mt-1">
            Cela peut prendre 15 a 30 secondes
          </p>
        </div>
      )}

      {/* Journal entries timeline */}
      {entries.length === 0 && !generating ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <BookOpen size={48} className="text-gray-700 mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2 text-gray-400">
            Aucune entree de journal
          </h3>
          <p className="text-gray-600 text-sm">
            Cliquez sur "Generer le journal du jour" pour creer votre premiere analyse de marche IA.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {entries.map((entry, index) => {
            const sentiment = SENTIMENT_STYLES[entry.sentiment || 'neutral'] || SENTIMENT_STYLES.neutral
            const isExpanded = expandedIds.has(entry.id)

            return (
              <div key={entry.id} className="relative">
                {/* Timeline connector */}
                {index < entries.length - 1 && (
                  <div className="absolute left-5 top-16 bottom-0 w-px bg-gray-800" style={{ transform: 'translateX(-50%)' }} />
                )}

                <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden hover:border-gray-700 transition">
                  {/* Header */}
                  <div
                    className="flex items-center gap-4 px-6 py-4 cursor-pointer"
                    onClick={() => toggleExpanded(entry.id)}
                  >
                    {/* Timeline dot */}
                    <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${sentiment.bg}`}>
                      <Calendar size={18} className={sentiment.text} />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3">
                        <h3 className="font-semibold text-sm">
                          {formatDate(entry.date)}
                        </h3>
                        <span className="text-xs text-gray-600">
                          {formatTime(entry.date)}
                        </span>
                      </div>
                      <p className="text-gray-500 text-xs mt-0.5 truncate">
                        {entry.summary.substring(0, 120)}...
                      </p>
                    </div>

                    {/* Sentiment badge */}
                    <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${sentiment.bg} ${sentiment.text}`}>
                      {sentiment.icon}
                      {sentiment.label}
                    </span>

                    {/* Model badge */}
                    {entry.model_used && (
                      <span className="text-xs text-gray-600 bg-gray-800 px-2 py-1 rounded hidden sm:block">
                        {entry.model_used}
                      </span>
                    )}

                    {/* Expand toggle */}
                    {isExpanded ? (
                      <ChevronUp size={18} className="text-gray-500 flex-shrink-0" />
                    ) : (
                      <ChevronDown size={18} className="text-gray-500 flex-shrink-0" />
                    )}
                  </div>

                  {/* Expanded content */}
                  {isExpanded && (
                    <div className="px-6 pb-5 border-t border-gray-800/50 pt-4 space-y-4">
                      {/* Summary */}
                      <div>
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                          Resume
                        </h4>
                        <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                          {entry.summary}
                        </div>
                      </div>

                      {/* Key events */}
                      {entry.key_events && entry.key_events.length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                            Evenements cles
                          </h4>
                          <ul className="space-y-1">
                            {entry.key_events.map((event, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm text-gray-400">
                                <span className="text-blue-400 mt-0.5 flex-shrink-0">&#8226;</span>
                                {event}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Market data snapshot */}
                      {entry.market_data && Object.keys(entry.market_data).length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                            Prix au moment du journal
                          </h4>
                          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                            {Object.entries(entry.market_data).map(([pair, data]) => (
                              <div
                                key={pair}
                                className="bg-gray-950 rounded-lg px-3 py-2 border border-gray-800"
                              >
                                <p className="text-xs text-gray-500 font-mono">
                                  {pair.replace('/USD', '')}
                                </p>
                                <p className="text-sm font-semibold text-gray-200">
                                  ${typeof data === 'object' && data !== null && 'last' in data
                                    ? Number(data.last).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                    : '—'}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
