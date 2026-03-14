import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Activity, DollarSign, TrendingUp, AlertTriangle } from 'lucide-react'

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

export default function Dashboard({ token }: DashboardProps) {
  const api = useApi(token)
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)

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
    }
    fetchData()
    const interval = setInterval(fetchData, 30000) // refresh every 30s
    return () => clearInterval(interval)
  }, [token])

  const closedTrades = trades.filter((t) => t.status === 'CLOSED')
  const openTrades = trades.filter((t) => t.status === 'OPEN')
  const totalPnl = closedTrades.reduce((s, t) => s + (t.profit || 0), 0)
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
      <h2 className="text-2xl font-bold mb-6">Dashboard</h2>

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
          value={String(openTrades.length)}
          color="purple"
        />
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
