import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Activity, DollarSign, TrendingUp, AlertTriangle, Wallet } from 'lucide-react'

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

export default function Dashboard({ token }: DashboardProps) {
  const api = useApi(token)
  const { lastMessage, connected } = useWebSocket('/ws/dashboard')
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

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, tradesRes, balanceRes] = await Promise.all([
          api.get('/bot/status'),
          api.get('/trades/?limit=20'),
          api.get('/bot/balance'),
        ])
        setBotStatus(statusRes.data)
        setTrades(tradesRes.data)
        if (balanceRes.data && !balanceRes.data.error) {
          setKrakenBalance(balanceRes.data)
        }
      } catch {
        // handle error
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 30000) // refresh every 30s
    return () => clearInterval(interval)
  }, [token])

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (!lastMessage) return

    const msg = lastMessage as WsMessage

    if (msg.type === 'status') {
      setLivePnl(msg.pnl)
      setLivePositions(msg.positions)
    } else if (msg.type === 'trade_opened') {
      const newTrade: Trade = {
        id: Date.now(), // temporary ID for display
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
  }, [lastMessage])

  const closedTrades = trades.filter((t) => t.status === 'CLOSED')
  const openTrades = trades.filter((t) => t.status === 'OPEN')
  const totalPnl = livePnl ?? closedTrades.reduce((s, t) => s + (t.profit || 0), 0)
  const winRate = closedTrades.length
    ? (closedTrades.filter((t) => (t.profit || 0) > 0).length /
        closedTrades.length) *
      100
    : 0

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
        <div className="flex items-center gap-2 text-sm">
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

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
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
      {krakenBalance && (
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
          <div className="grid grid-cols-3 gap-4 mb-4">
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
        </div>
      )}

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
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
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
            {trades.slice(0, 10).map((t) => (
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
            ))}
          </tbody>
        </table>
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
