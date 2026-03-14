import { useEffect, useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Globe, Loader2, RefreshCw, ChevronDown, ChevronUp,
  TrendingUp, TrendingDown, AlertTriangle, Shield, Activity,
} from 'lucide-react'

/* ── Types ─────────────────────────────────────────────── */

interface Market {
  id: string
  question: string
  probability: number
  volume: number
  category: string
  related_pair: string | null
}

interface Sentiment {
  overall_score: number
  risk_level: string
  key_factors: string[]
}

interface PairSentiment {
  pair: string
  bullish_probability: number
  bearish_probability: number
  confidence: number
  market_count: number
  total_volume: number
  related_markets: {
    question: string
    probability: number
    volume: number
    category: string
  }[]
}

const PAIRS = [
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD',
  'DOT/USD', 'AVAX/USD', 'LINK/USD', 'MATIC/USD', 'ATOM/USD',
]

/* ── Helpers ───────────────────────────────────────────── */

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
  return `$${v}`
}

function probColor(p: number): string {
  if (p >= 0.6) return 'text-green-400'
  if (p <= 0.4) return 'text-red-400'
  return 'text-gray-400'
}

function probBg(p: number): string {
  if (p >= 0.6) return 'bg-green-500'
  if (p <= 0.4) return 'bg-red-500'
  return 'bg-gray-500'
}

function probBorder(p: number): string {
  if (p >= 0.6) return 'border-green-500/30'
  if (p <= 0.4) return 'border-red-500/30'
  return 'border-gray-600'
}

function riskColor(level: string): string {
  switch (level) {
    case 'Low': return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'Medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
    case 'High': return 'bg-red-500/20 text-red-400 border-red-500/30'
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  }
}

function categoryBadge(cat: string): string {
  switch (cat) {
    case 'Crypto': return 'bg-blue-500/20 text-blue-400'
    case 'Regulation': return 'bg-purple-500/20 text-purple-400'
    case 'Macro': return 'bg-orange-500/20 text-orange-400'
    case 'DeFi': return 'bg-cyan-500/20 text-cyan-400'
    default: return 'bg-gray-500/20 text-gray-400'
  }
}

/* ── Gauge Component ───────────────────────────────────── */

function SentimentGauge({ score }: { score: number }) {
  const angle = (score / 100) * 180 - 90
  const gaugeColor =
    score >= 65 ? '#22c55e' : score >= 40 ? '#eab308' : '#ef4444'

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 120" className="w-48 h-28">
        {/* Background arc */}
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke="#374151"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke={gaugeColor}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${(score / 100) * 251.3} 251.3`}
        />
        {/* Needle */}
        <line
          x1="100"
          y1="100"
          x2={100 + 60 * Math.cos((angle * Math.PI) / 180)}
          y2={100 - 60 * Math.sin((angle * Math.PI) / 180)}
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="100" cy="100" r="4" fill="white" />
        {/* Score text */}
        <text x="100" y="85" textAnchor="middle" fill="white" fontSize="28" fontWeight="bold">
          {score}
        </text>
        {/* Labels */}
        <text x="20" y="115" textAnchor="middle" fill="#9ca3af" fontSize="10">
          0
        </text>
        <text x="100" y="30" textAnchor="middle" fill="#9ca3af" fontSize="10">
          50
        </text>
        <text x="180" y="115" textAnchor="middle" fill="#9ca3af" fontSize="10">
          100
        </text>
      </svg>
      <p className="text-sm text-gray-400 mt-1">Crypto Sentiment Score</p>
    </div>
  )
}

/* ── Main Component ────────────────────────────────────── */

export default function Polymarket({ token }: { token: string }) {
  const api = useApi(token)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [markets, setMarkets] = useState<Market[]>([])
  const [sentiment, setSentiment] = useState<Sentiment | null>(null)
  const [selectedPair, setSelectedPair] = useState('BTC/USD')
  const [pairData, setPairData] = useState<PairSentiment | null>(null)
  const [pairLoading, setPairLoading] = useState(false)
  const [expandedMarket, setExpandedMarket] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      const [trendsRes, sentimentRes] = await Promise.all([
        api.get('/polymarket/trends'),
        api.get('/polymarket/sentiment'),
      ])
      setMarkets(trendsRes.data)
      setSentiment(sentimentRes.data)
      setLastRefresh(new Date())
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [api])

  const loadPairData = useCallback(async (pair: string) => {
    setPairLoading(true)
    try {
      const res = await api.get(`/polymarket/pair/${encodeURIComponent(pair)}`)
      setPairData(res.data)
    } catch {
      setPairData(null)
    } finally {
      setPairLoading(false)
    }
  }, [api])

  // Initial load
  useEffect(() => { loadData() }, [])

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(() => loadData(true), 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [loadData])

  // Load pair data when selection changes
  useEffect(() => { loadPairData(selectedPair) }, [selectedPair])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-blue-400" size={32} />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Globe size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Polymarket Trends</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">
            Last refresh: {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 text-sm transition disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Macro Sentiment Card ────────────────────────── */}
      {sentiment && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={18} className="text-blue-400" />
            <h3 className="font-semibold text-lg">Macro Crypto Sentiment</h3>
          </div>
          <div className="flex flex-col md:flex-row items-center gap-8">
            {/* Gauge */}
            <SentimentGauge score={sentiment.overall_score} />

            {/* Risk level + factors */}
            <div className="flex-1 space-y-4">
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-400">Risk Level:</span>
                <span
                  className={`px-3 py-1 rounded-full text-sm font-medium border ${riskColor(sentiment.risk_level)}`}
                >
                  {sentiment.risk_level === 'Low' && <Shield className="inline mr-1" size={14} />}
                  {sentiment.risk_level === 'Medium' && <AlertTriangle className="inline mr-1" size={14} />}
                  {sentiment.risk_level === 'High' && <AlertTriangle className="inline mr-1" size={14} />}
                  {sentiment.risk_level}
                </span>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-2">Key Factors:</p>
                <ul className="space-y-1.5">
                  {sentiment.key_factors.map((f, i) => (
                    <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                      <span className="text-blue-400 mt-1 shrink-0">&#8226;</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Trending Markets Section ───────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={18} className="text-blue-400" />
          <h3 className="font-semibold text-lg">Trending Prediction Markets</h3>
        </div>

        {markets.length === 0 ? (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
            <Globe size={48} className="text-gray-700 mx-auto mb-4" />
            <p className="text-gray-500">No trending markets available</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {markets.map(m => {
              const isExpanded = expandedMarket === m.id
              const pct = Math.round(m.probability * 100)
              return (
                <div
                  key={m.id}
                  className={`bg-gray-900 rounded-xl border ${probBorder(m.probability)} p-4 transition hover:border-gray-500 cursor-pointer`}
                  onClick={() => setExpandedMarket(isExpanded ? null : m.id)}
                >
                  {/* Category + probability */}
                  <div className="flex items-center justify-between mb-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${categoryBadge(m.category)}`}>
                      {m.category}
                    </span>
                    <span className={`text-lg font-bold ${probColor(m.probability)}`}>
                      {pct}%
                    </span>
                  </div>

                  {/* Question */}
                  <p className="text-sm text-gray-200 mb-3 leading-relaxed">
                    {m.question}
                  </p>

                  {/* Probability bar */}
                  <div className="w-full bg-gray-700 rounded-full h-2 mb-3">
                    <div
                      className={`h-2 rounded-full transition-all ${probBg(m.probability)}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>

                  {/* Volume + expand indicator */}
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>Vol: {formatVolume(m.volume)}</span>
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-gray-700 space-y-2">
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-400">Probability</span>
                        <span className={probColor(m.probability)}>{(m.probability * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-400">Volume</span>
                        <span className="text-gray-300">{formatVolume(m.volume)}</span>
                      </div>
                      {m.related_pair && (
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-400">Related Pair</span>
                          <span className="text-blue-400">{m.related_pair}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-400">Signal</span>
                        <span className={probColor(m.probability)}>
                          {m.probability >= 0.6 ? 'Bullish' : m.probability <= 0.4 ? 'Bearish' : 'Neutral'}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Pair Sentiment Section ─────────────────────── */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <TrendingDown size={18} className="text-blue-400" />
            <h3 className="font-semibold text-lg">Pair Sentiment</h3>
          </div>
          <select
            value={selectedPair}
            onChange={e => setSelectedPair(e.target.value)}
            className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
          >
            {PAIRS.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        {pairLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-blue-400" size={24} />
          </div>
        ) : pairData ? (
          <div className="space-y-6">
            {/* Bullish vs Bearish bar */}
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-green-400 font-medium flex items-center gap-1">
                  <TrendingUp size={14} />
                  Bullish {(pairData.bullish_probability * 100).toFixed(1)}%
                </span>
                <span className="text-red-400 font-medium flex items-center gap-1">
                  Bearish {(pairData.bearish_probability * 100).toFixed(1)}%
                  <TrendingDown size={14} />
                </span>
              </div>
              <div className="w-full flex h-4 rounded-full overflow-hidden">
                <div
                  className="bg-green-500 transition-all"
                  style={{ width: `${pairData.bullish_probability * 100}%` }}
                />
                <div
                  className="bg-red-500 transition-all"
                  style={{ width: `${pairData.bearish_probability * 100}%` }}
                />
              </div>
            </div>

            {/* Confidence + stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-gray-800 rounded-lg p-4 text-center">
                <p className="text-xs text-gray-500 uppercase mb-1">Confidence</p>
                <p className="text-2xl font-bold text-blue-400">{pairData.confidence}%</p>
                <div className="w-full bg-gray-700 rounded-full h-1.5 mt-2">
                  <div
                    className="bg-blue-500 h-1.5 rounded-full"
                    style={{ width: `${pairData.confidence}%` }}
                  />
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 text-center">
                <p className="text-xs text-gray-500 uppercase mb-1">Markets Analyzed</p>
                <p className="text-2xl font-bold text-gray-200">{pairData.market_count}</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 text-center">
                <p className="text-xs text-gray-500 uppercase mb-1">Total Volume</p>
                <p className="text-2xl font-bold text-gray-200">{formatVolume(pairData.total_volume)}</p>
              </div>
            </div>

            {/* Related markets */}
            {pairData.related_markets.length > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-3">Related Markets</p>
                <div className="space-y-2">
                  {pairData.related_markets.map((rm, i) => {
                    const rmPct = Math.round(rm.probability * 100)
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-4 bg-gray-800 rounded-lg px-4 py-3"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-200 truncate">{rm.question}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${categoryBadge(rm.category)}`}>
                              {rm.category}
                            </span>
                            <span className="text-xs text-gray-500">
                              {formatVolume(rm.volume)}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <div className="w-20 bg-gray-700 rounded-full h-1.5">
                            <div
                              className={`h-1.5 rounded-full ${probBg(rm.probability)}`}
                              style={{ width: `${rmPct}%` }}
                            />
                          </div>
                          <span className={`text-sm font-bold w-12 text-right ${probColor(rm.probability)}`}>
                            {rmPct}%
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {pairData.related_markets.length === 0 && (
              <div className="text-center py-6">
                <p className="text-gray-500 text-sm">No related markets found for {selectedPair}</p>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-6">
            <p className="text-gray-500 text-sm">Failed to load pair sentiment data</p>
          </div>
        )}
      </div>
    </div>
  )
}
