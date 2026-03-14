import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { TrendingUp, TrendingDown, BarChart3, Activity, Loader2 } from 'lucide-react'

interface EquityPoint { date: string; balance: number; pnl: number; cumulative_pnl: number }
interface DrawdownPoint { date: string; drawdown_pct: number; max_balance: number }
interface DayPnl { date: string; pnl: number; trades: number }
interface StratPnl { strategy: string; pnl: number; trades: number; win_rate: number }
interface PairPnl { pair: string; pnl: number; trades: number; win_rate: number }
interface PerfSummary {
  total_pnl: number; win_rate: number; profit_factor: number | null
  avg_win: number; avg_loss: number; max_drawdown: number
  sharpe_ratio: number | null; best_day: number; worst_day: number
  avg_trades_per_day: number
}

export default function Analytics({ token }: { token: string }) {
  const api = useApi(token)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [equity, setEquity] = useState<EquityPoint[]>([])
  const [drawdown, setDrawdown] = useState<DrawdownPoint[]>([])
  const [byDay, setByDay] = useState<DayPnl[]>([])
  const [byStrategy, setByStrategy] = useState<StratPnl[]>([])
  const [byPair, setByPair] = useState<PairPnl[]>([])
  const [summary, setSummary] = useState<PerfSummary | null>(null)

  useEffect(() => { loadAll() }, [days])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [eq, dd, bd, ps] = await Promise.all([
        api.get(`/analytics/equity-curve?days=${days}`),
        api.get(`/analytics/drawdown?days=${days}`),
        api.get(`/analytics/pnl-breakdown?days=${days}`),
        api.get(`/analytics/performance-summary?days=${days}`),
      ])
      setEquity(eq.data)
      setDrawdown(dd.data)
      setByDay(bd.data.by_day)
      setByStrategy(bd.data.by_strategy)
      setByPair(bd.data.by_pair)
      setSummary(ps.data)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color || 'text-white'}`}>{value}</p>
    </div>
  )

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin text-blue-400" size={32} />
    </div>
  )

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Analytics</h2>
        </div>
        <select
          value={days}
          onChange={e => setDays(Number(e.target.value))}
          className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
        >
          <option value={7}>7 jours</option>
          <option value={14}>14 jours</option>
          <option value={30}>30 jours</option>
          <option value={90}>90 jours</option>
          <option value={180}>6 mois</option>
          <option value={365}>1 an</option>
        </select>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <Stat label="P&L Total" value={`$${summary.total_pnl.toFixed(2)}`} color={summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'} />
          <Stat label="Win Rate" value={`${summary.win_rate}%`} color={summary.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'} />
          <Stat label="Profit Factor" value={summary.profit_factor !== null ? summary.profit_factor.toFixed(2) : 'N/A'} />
          <Stat label="Max Drawdown" value={`${summary.max_drawdown.toFixed(1)}%`} color="text-red-400" />
          <Stat label="Sharpe Ratio" value={summary.sharpe_ratio !== null ? summary.sharpe_ratio.toFixed(2) : 'N/A'} />
          <Stat label="Gain moyen" value={`$${summary.avg_win.toFixed(2)}`} color="text-green-400" />
          <Stat label="Perte moyenne" value={`$${summary.avg_loss.toFixed(2)}`} color="text-red-400" />
          <Stat label="Meilleur jour" value={`$${summary.best_day.toFixed(2)}`} color="text-green-400" />
          <Stat label="Pire jour" value={`$${summary.worst_day.toFixed(2)}`} color="text-red-400" />
          <Stat label="Trades/jour" value={summary.avg_trades_per_day.toFixed(1)} />
        </div>
      )}

      {/* Equity Curve */}
      {equity.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={18} className="text-blue-400" />
            <h3 className="font-semibold">Courbe d'equity</h3>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={equity}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
              <Area type="monotone" dataKey="cumulative_pnl" stroke="#3b82f6" fill="#3b82f620" name="P&L cumulatif" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Daily PnL */}
      {byDay.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={18} className="text-blue-400" />
            <h3 className="font-semibold">P&L journalier</h3>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={byDay}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
              <Bar dataKey="pnl" name="P&L">
                {byDay.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Drawdown */}
      {drawdown.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown size={18} className="text-red-400" />
            <h3 className="font-semibold">Drawdown</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={drawdown}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} unit="%" />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
              <Area type="monotone" dataKey="drawdown_pct" stroke="#ef4444" fill="#ef444420" name="Drawdown %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* By Strategy + By Pair */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {byStrategy.length > 0 && (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <h3 className="font-semibold mb-4">Performance par strategie</h3>
            <div className="space-y-3">
              {byStrategy.map(s => (
                <div key={s.strategy} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium">{s.strategy}</span>
                    <span className="text-gray-500 ml-2">({s.trades} trades)</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-400">{s.win_rate}% WR</span>
                    <span className={`font-bold ${s.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${s.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {byPair.length > 0 && (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <h3 className="font-semibold mb-4">Performance par paire</h3>
            <div className="space-y-3">
              {byPair.map(p => (
                <div key={p.pair} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium">{p.pair}</span>
                    <span className="text-gray-500 ml-2">({p.trades} trades)</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-400">{p.win_rate}% WR</span>
                    <span className={`font-bold ${p.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${p.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Empty state */}
      {equity.length === 0 && !loading && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <BarChart3 size={48} className="text-gray-700 mx-auto mb-4" />
          <p className="text-gray-500">Aucune donnee de trading pour cette periode</p>
          <p className="text-gray-600 text-sm mt-1">Les graphiques apparaitront apres vos premiers trades</p>
        </div>
      )}
    </div>
  )
}
