import { useEffect, useState, useRef } from 'react'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { useTradeNotifications } from '../hooks/useNotifications'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Activity, DollarSign, TrendingUp, AlertTriangle, Wallet, Terminal, BarChart3 } from 'lucide-react'

interface DashboardProps {
  token: string
}

interface BotStatus {
  status: string
  details: string
}

interface Trade {
  id: number
  pair: string
  direction: string
  profit: number | null
  status: string
  opened_at: string
}

interface LogEntry {
  timestamp: string
  level: string
  event: string
  [key: string]: unknown
}

interface CryptoPrice {
  pair: string
  last: number
  bid: number
  ask: number
  spread: number
  volume: number
}

interface AIStatusData {
  enabled: boolean
  configured: boolean
  model: string
}

interface WsStatusMessage {
  type: 'status'
  balance: number
  pnl: number
  positions: number
}

interface WsTradeOpenedMessage {
  type: 'trade_opened'
  pair: string
  direction: string
  price: number
  size: number
  strategy: string
}

interface WsTradeClosedMessage {
  type: 'trade_closed'
  pair: string
  profit: number
  exit_price: number
}

type WsMessage = WsStatusMessage | WsTradeOpenedMessage | WsTradeClosedMessage

const LOG_LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-500',
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
}

export default function Dashboard({ token }: DashboardProps) {
  const api = useApi(token)
  const { lastMessage: dashMsg, connected } = useWebSocket('/ws/dashboard')
  const { lastMessage: logMsg } = useWebSocket('/ws/logs')
  useTradeNotifications(dashMsg)
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)

  // Live metrics from WebSocket
  const [livePnl, setLivePnl] = useState<number | null>(null)
  const [livePositions, setLivePositions] = useState<number | null>(null)

  // Real Kraken balance
  const [krakenBalance, setKrakenBalance] = useState<{
    total_balance: number
    available_balance: number
    open_positions: number
    positions: { pair: string; direction: string; size: number; entry_price: number; unrealized_pnl: number }[]
  } | null>(null)
  const [balanceError, setBalanceError] = useState<string | null>(null)

  // Crypto prices
  const [prices, setPrices] = useState<CryptoPrice[]>([])

  // AI status
  const [aiStatus, setAiStatus] = useState<AIStatusData | null>(null)

  // Autopilot scores
  const [autopilotScores, setAutopilotScores] = useState<{
    all_scores: {
      pair: string; composite: number; trend: number; momentum: number;
      volatility: number; alignment: number; regime: string; direction: string;
      strategy: string; active: boolean
    }[]
    active_count: number; total_scanned: number
  } | null>(null)

  // Autopilot toggle
  const [autopilotEnabled, setAutopilotEnabled] = useState(false)
  const [autopilotToggling, setAutopilotToggling] = useState(false)

  // Bot logs
  const [logs, setLogs] = useState<LogEntry[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, tradesRes] = await Promise.all([
          api.get('/bot/status'),
          api.get('/trades/?limit=20'),
        ])
        setBotStatus(statusRes.data)
        setTrades(tradesRes.data)
      } catch {
        // handle error
      } finally {
        setLoading(false)
      }

      // Fetch balance, prices, AI status separately so they don't block the rest
      try {
        const balanceRes = await api.get('/bot/balance')
        if (balanceRes.data && !balanceRes.data.error) {
          setKrakenBalance(balanceRes.data)
          setBalanceError(null)
        } else if (balanceRes.data?.error) {
          setBalanceError(balanceRes.data.error)
        }
      } catch {
        setBalanceError('Impossible de recuperer le solde')
      }

      try {
        const pricesRes = await api.get('/markets/prices')
        if (Array.isArray(pricesRes.data)) setPrices(pricesRes.data)
      } catch { /* prices not available */ }

      try {
        const aiRes = await api.get('/ai/status')
        if (aiRes.data) setAiStatus(aiRes.data)
      } catch { /* ai not available */ }

      try {
        const apRes = await api.get('/bot/autopilot/scores')
        if (apRes.data) setAutopilotScores(apRes.data)
      } catch { /* autopilot not available */ }

      // Load autopilot enabled state from settings
      try {
        const settingsRes = await api.get('/settings/schema')
        if (settingsRes.data?.autopilot) {
          const apSetting = settingsRes.data.autopilot.autopilot_enabled
          if (apSetting) {
            const val = String(apSetting.value).toLowerCase()
            setAutopilotEnabled(val === 'true' || val === '1' || val === 'yes' || val === 'on')
          }
        }
      } catch { /* settings not available */ }
    }
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [token])

  // Load log history
  useEffect(() => {
    const loadLogs = async () => {
      try {
        const res = await api.get('/bot/logs?limit=50')
        if (Array.isArray(res.data)) {
          setLogs(res.data.reverse())
        }
      } catch {
        // logs might not be available yet
      }
    }
    loadLogs()
  }, [token])

  // Handle dashboard WebSocket messages
  useEffect(() => {
    if (!dashMsg) return
    const msg = dashMsg as WsMessage
    if (msg.type === 'status') {
      setLivePnl(msg.pnl)
      setLivePositions(msg.positions)
    } else if (msg.type === 'trade_opened') {
      const newTrade: Trade = {
        id: Date.now(),
        pair: msg.pair,
        direction: msg.direction,
        profit: null,
        status: 'OPEN',
        opened_at: new Date().toISOString(),
      }
      setTrades((prev) => [newTrade, ...prev].slice(0, 20))
    } else if (msg.type === 'trade_closed') {
      setTrades((prev) =>
        prev.map((t) =>
          t.pair === msg.pair && t.status === 'OPEN'
            ? { ...t, status: 'CLOSED', profit: msg.profit }
            : t,
        ),
      )
    }
  }, [dashMsg])

  // Handle log WebSocket messages
  useEffect(() => {
    if (!logMsg) return
    const entry = logMsg as LogEntry
    if (entry.event && entry.event !== 'heartbeat' && entry.level) {
      setLogs((prev) => [...prev.slice(-99), entry])
    }
  }, [logMsg])

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const closedTrades = trades.filter((t) => t.status === 'CLOSED')
  const openTrades = trades.filter((t) => t.status === 'OPEN')
  const totalPnl = livePnl ?? closedTrades.reduce((s, t) => s + (t.profit || 0), 0)
  const winRate = closedTrades.length
    ? (closedTrades.filter((t) => (t.profit || 0) > 0).length /
        closedTrades.length) *
      100
    : 0

  const handleToggleAutopilot = async () => {
    setAutopilotToggling(true)
    try {
      const newVal = !autopilotEnabled
      await api.put('/settings/', { key: 'autopilot_enabled', value: String(newVal) })
      setAutopilotEnabled(newVal)
      // Trigger immediate scan if enabling
      if (newVal) {
        await api.post('/bot/autopilot/scan')
      }
    } catch {
      // revert on error
    } finally {
      setAutopilotToggling(false)
    }
  }

  const pnlData = closedTrades
    .slice()
    .reverse()
    .reduce(
      (acc: { name: string; pnl: number }[], t, i) => {
        const prev = i > 0 ? acc[i - 1].pnl : 0
        acc.push({ name: `#${i + 1}`, pnl: prev + (t.profit || 0) })
        return acc
      },
      [],
    )

  if (loading) {
    return <p className="text-gray-400">Loading...</p>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <div className="flex items-center gap-3 text-sm">
          {/* AI Status badge */}
          {aiStatus && (
            <span
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
                aiStatus.enabled && aiStatus.configured
                  ? 'bg-purple-500/20 text-purple-400'
                  : 'bg-gray-700 text-gray-400'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                aiStatus.enabled && aiStatus.configured ? 'bg-purple-400' : 'bg-gray-500'
              }`} />
              IA {aiStatus.enabled && aiStatus.configured ? 'ON' : 'OFF'}
              {aiStatus.configured && aiStatus.model && (
                <span className="text-gray-500 ml-1">({aiStatus.model.replace('claude-', '').split('-')[0]})</span>
              )}
            </span>
          )}
          {/* Live status */}
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                connected ? 'bg-green-400' : 'bg-red-400'
              }`}
            />
            <span className={connected ? 'text-green-400' : 'text-red-400'}>
              {connected ? 'Live' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={<Activity size={20} />}
          label="Bot Status"
          value={botStatus?.status || 'unknown'}
          color="blue"
        />
        <StatCard
          icon={<DollarSign size={20} />}
          label="Total P&L"
          value={`$${totalPnl.toFixed(2)}`}
          color={totalPnl >= 0 ? 'green' : 'red'}
        />
        <StatCard
          icon={<TrendingUp size={20} />}
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          color="yellow"
        />
        <StatCard
          icon={<AlertTriangle size={20} />}
          label="Open Positions"
          value={String(livePositions ?? openTrades.length)}
          color="purple"
        />
      </div>

      {/* Kraken Account Balance */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="inline-flex p-2 rounded-lg bg-blue-500/10 text-blue-400">
            <Wallet size={20} />
          </div>
          <div>
            <h3 className="font-semibold">Compte Kraken</h3>
            <p className="text-xs text-gray-500">Solde en temps reel</p>
          </div>
        </div>
        {krakenBalance ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div>
                <p className="text-gray-500 text-xs mb-1">Solde total</p>
                <p className="text-2xl font-bold font-mono">${krakenBalance.total_balance.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs mb-1">Disponible</p>
                <p className="text-lg font-bold font-mono text-green-400">${krakenBalance.available_balance.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs mb-1">Positions ouvertes</p>
                <p className="text-lg font-bold">{krakenBalance.open_positions}</p>
              </div>
            </div>
            {krakenBalance.positions.length > 0 && (
              <div className="border-t border-gray-800 pt-3">
                <p className="text-xs text-gray-500 mb-2">Positions actives</p>
                <div className="space-y-2">
                  {krakenBalance.positions.map((p, i) => (
                    <div key={i} className="flex items-center justify-between text-sm bg-gray-800/50 rounded-lg px-3 py-2">
                      <span className="font-mono">{p.pair}</span>
                      <span className={p.direction === 'buy' ? 'text-green-400' : 'text-red-400'}>
                        {p.direction.toUpperCase()}
                      </span>
                      <span className="text-gray-400">Size: {p.size}</span>
                      <span className="text-gray-400">Entry: ${p.entry_price.toFixed(2)}</span>
                      <span className={p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                        {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl.toFixed(2)} $
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="text-gray-500 text-sm">
            {balanceError || 'Chargement du solde...'}
          </p>
        )}
      </div>

      {/* Crypto Prices – horizontal scrolling ticker */}
      {prices.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden mb-8">
          <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-800/30">
            <BarChart3 size={18} className="text-blue-400" />
            <h3 className="font-semibold">Marche Crypto</h3>
            <span className="text-xs text-gray-500 ml-auto">{prices.length} paires · Prix en temps reel</span>
          </div>
          <div className="relative overflow-hidden">
            <div className="flex animate-marquee hover:[animation-play-state:paused] gap-0">
              {[...prices, ...prices].map((p, idx) => {
                const symbol = p.pair.replace('/USD', '')
                return (
                  <div
                    key={`${p.pair}-${idx}`}
                    className="flex-shrink-0 w-48 px-4 py-3 border-r border-gray-800/50 hover:bg-gray-800/30 transition"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono font-semibold text-sm">{symbol}</span>
                      <span className="text-xs text-gray-600">USD</span>
                    </div>
                    <p className="text-lg font-bold font-mono">
                      {p.last >= 1
                        ? `$${p.last.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : `$${p.last.toFixed(6)}`}
                    </p>
                    <div className="flex items-center justify-between mt-1 text-xs text-gray-500">
                      <span>Spread: {p.spread < 0.01 ? p.spread.toFixed(6) : `$${p.spread.toFixed(2)}`}</span>
                      <span>Vol: {p.volume >= 1_000_000 ? `${(p.volume / 1_000_000).toFixed(1)}M` : p.volume >= 1000 ? `${(p.volume / 1000).toFixed(1)}K` : p.volume.toFixed(1)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Autopilot - Trend Analysis */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden mb-8">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-800/30">
          <div className="flex items-center gap-3">
            <Activity size={18} className="text-yellow-400" />
            <div>
              <h3 className="font-semibold">Autopilot – Analyse des tendances</h3>
              <p className="text-xs text-gray-500">
                {autopilotScores && autopilotScores.total_scanned > 0
                  ? `${autopilotScores.total_scanned} paires scannees · ${autopilotScores.active_count} actives`
                  : 'Aucun scan effectue'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Toggle switch */}
            <button
              onClick={handleToggleAutopilot}
              disabled={autopilotToggling}
              className="flex items-center gap-2.5 cursor-pointer disabled:opacity-50"
            >
              <span className={`text-xs font-medium ${autopilotEnabled ? 'text-green-400' : 'text-gray-500'}`}>
                {autopilotEnabled ? 'ON' : 'OFF'}
              </span>
              <div className={`relative w-11 h-6 rounded-full transition-colors ${
                autopilotEnabled ? 'bg-green-600' : 'bg-gray-700'
              }`}>
                <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  autopilotEnabled ? 'translate-x-[22px]' : 'translate-x-0.5'
                }`} />
              </div>
            </button>
            {autopilotEnabled && (
              <button
                onClick={() => api.post('/bot/autopilot/scan')}
                className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-xs font-medium transition"
              >
                Relancer le scan
              </button>
            )}
          </div>
        </div>
        {autopilotScores && autopilotScores.all_scores.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800 text-xs">
                  <th className="text-left px-4 py-2">Paire</th>
                  <th className="text-center px-2 py-2">Score</th>
                  <th className="text-center px-2 py-2">Tendance</th>
                  <th className="text-center px-2 py-2">Momentum</th>
                  <th className="text-center px-2 py-2">Volatilite</th>
                  <th className="text-center px-2 py-2">Alignement</th>
                  <th className="text-center px-2 py-2">Regime</th>
                  <th className="text-center px-2 py-2">Direction</th>
                  <th className="text-center px-2 py-2">Strategie</th>
                  <th className="text-center px-2 py-2">Statut</th>
                </tr>
              </thead>
              <tbody>
                {autopilotScores.all_scores.map((s) => (
                  <tr key={s.pair} className={`border-b border-gray-800/30 ${s.active ? 'bg-yellow-500/5' : ''}`}>
                    <td className="px-4 py-2 font-mono font-semibold">{s.pair}</td>
                    <td className="text-center px-2 py-2">
                      <span className={`font-bold ${
                        s.composite >= 0.7 ? 'text-green-400' : s.composite >= 0.55 ? 'text-yellow-400' : 'text-gray-500'
                      }`}>
                        {(s.composite * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="text-center px-2 py-2"><ScoreBar value={s.trend} /></td>
                    <td className="text-center px-2 py-2"><ScoreBar value={s.momentum} /></td>
                    <td className="text-center px-2 py-2"><ScoreBar value={s.volatility} /></td>
                    <td className="text-center px-2 py-2"><ScoreBar value={s.alignment} /></td>
                    <td className="text-center px-2 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        s.regime === 'trending' ? 'bg-green-500/10 text-green-400' :
                        s.regime === 'volatile' ? 'bg-red-500/10 text-red-400' :
                        'bg-gray-700 text-gray-400'
                      }`}>
                        {s.regime}
                      </span>
                    </td>
                    <td className="text-center px-2 py-2">
                      <span className={`text-xs font-medium ${
                        s.direction === 'bullish' ? 'text-green-400' :
                        s.direction === 'bearish' ? 'text-red-400' :
                        'text-gray-500'
                      }`}>
                        {s.direction === 'bullish' ? 'BULL' : s.direction === 'bearish' ? 'BEAR' : '—'}
                      </span>
                    </td>
                    <td className="text-center px-2 py-2 text-xs text-gray-400">
                      {s.strategy || '—'}
                    </td>
                    <td className="text-center px-2 py-2">
                      {s.active ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-400">Active</span>
                      ) : (
                        <span className="text-xs text-gray-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-8 text-center">
            <Activity size={32} className="text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">
              {autopilotEnabled
                ? 'Scan en cours... Les resultats apparaitront ici.'
                : 'Activez l\'autopilot pour scanner automatiquement les 40+ paires et detecter les meilleures opportunites.'}
            </p>
          </div>
        )}
      </div>

      {/* Equity curve */}
      {pnlData.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
          <h3 className="text-lg font-semibold mb-4">Equity Curve</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={pnlData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" stroke="#6B7280" />
              <YAxis stroke="#6B7280" />
              <Tooltip
                contentStyle={{
                  background: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                }}
              />
              <Line
                type="monotone"
                dataKey="pnl"
                stroke="#3B82F6"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent trades */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h3 className="text-lg font-semibold mb-4">Recent Trades</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-2">Pair</th>
              <th className="text-left py-2">Direction</th>
              <th className="text-left py-2">Status</th>
              <th className="text-right py-2">P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-4 text-center text-gray-500">Aucun trade</td>
              </tr>
            ) : (
              trades.slice(0, 10).map((t) => (
                <tr key={t.id} className="border-b border-gray-800/50">
                  <td className="py-2 font-mono">{t.pair}</td>
                  <td className="py-2">
                    <span
                      className={
                        t.direction === 'buy' ? 'text-green-400' : 'text-red-400'
                      }
                    >
                      {t.direction.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400">{t.status}</td>
                  <td className="py-2 text-right font-mono">
                    {t.profit != null ? (
                      <span
                        className={
                          t.profit >= 0 ? 'text-green-400' : 'text-red-400'
                        }
                      >
                        ${t.profit.toFixed(2)}
                      </span>
                    ) : (
                      '–'
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bot Logs */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-800/30">
          <Terminal size={18} className="text-green-400" />
          <h3 className="font-semibold">Bot Logs</h3>
          <span className="text-xs text-gray-500 ml-auto">{logs.length} entries</span>
        </div>
        <div className="h-64 overflow-auto font-mono text-xs p-4 bg-gray-950">
          {logs.length === 0 ? (
            <p className="text-gray-600 text-center py-8">
              En attente des logs du bot...
            </p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-2 py-0.5 hover:bg-gray-900/50">
                <span className="text-gray-600 whitespace-nowrap">
                  {formatLogTime(log.timestamp)}
                </span>
                <span className={`w-12 text-right shrink-0 ${LOG_LEVEL_COLORS[log.level] || 'text-gray-400'}`}>
                  {log.level}
                </span>
                <span className="text-purple-400 font-semibold shrink-0">{log.event}</span>
                <span className="text-gray-400 truncate">{formatLogExtra(log)}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  )
}

function formatLogTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatLogExtra(log: LogEntry): string {
  const skip = new Set(['timestamp', 'level', 'event', 'type'])
  const parts: string[] = []
  for (const [k, v] of Object.entries(log)) {
    if (skip.has(k)) continue
    parts.push(`${k}=${v}`)
  }
  return parts.join(' ')
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'bg-green-500' : pct >= 45 ? 'bg-yellow-500' : 'bg-gray-600'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-12 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-7">{pct}%</span>
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
    yellow: 'text-yellow-400 bg-yellow-500/10',
    purple: 'text-purple-400 bg-purple-500/10',
  }
  const cls = colors[color] || colors.blue

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className={`inline-flex p-2 rounded-lg ${cls} mb-3`}>{icon}</div>
      <p className="text-gray-500 text-xs mb-1">{label}</p>
      <p className="text-xl font-bold">{value}</p>
    </div>
  )
}
