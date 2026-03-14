import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { GitCompareArrows, Loader2 } from 'lucide-react'

interface StrategyMetrics {
  strategy: string
  total_trades: number
  win_count: number
  loss_count: number
  win_rate: number
  total_pnl: number
  avg_profit: number
  max_win: number
  max_loss: number
  profit_factor: number | null
  avg_holding_hours: number | null
}

export default function StrategyComparison({ token }: { token: string }) {
  const api = useApi(token)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<StrategyMetrics[]>([])

  useEffect(() => { loadData() }, [days])

  const loadData = async () => {
    setLoading(true)
    try {
      const res = await api.get(`/analytics/strategy-comparison?days=${days}`)
      setData(res.data)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  const pnlColor = (v: number) => v >= 0 ? 'text-green-400' : 'text-red-400'

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
          <GitCompareArrows size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Comparaison des strategies</h2>
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
          <option value={365}>1 an</option>
        </select>
      </div>

      {/* PnL Bar Chart */}
      {data.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h3 className="font-semibold mb-4">P&L par strategie</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="strategy" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
              <Bar dataKey="total_pnl" name="P&L Total">
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.total_pnl >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Comparison Table */}
      {data.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 overflow-x-auto">
          <h3 className="font-semibold mb-4">Metriques detaillees</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs uppercase border-b border-gray-800">
                <th className="text-left py-3 px-2">Strategie</th>
                <th className="text-right py-3 px-2">Trades</th>
                <th className="text-right py-3 px-2">Wins</th>
                <th className="text-right py-3 px-2">Losses</th>
                <th className="text-right py-3 px-2">Win Rate</th>
                <th className="text-right py-3 px-2">P&L Total</th>
                <th className="text-right py-3 px-2">Moy. / Trade</th>
                <th className="text-right py-3 px-2">Max Win</th>
                <th className="text-right py-3 px-2">Max Loss</th>
                <th className="text-right py-3 px-2">Profit Factor</th>
                <th className="text-right py-3 px-2">Duree Moy.</th>
              </tr>
            </thead>
            <tbody>
              {data.map(s => (
                <tr key={s.strategy} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition">
                  <td className="py-3 px-2 font-medium">{s.strategy}</td>
                  <td className="text-right py-3 px-2 text-gray-400">{s.total_trades}</td>
                  <td className="text-right py-3 px-2 text-green-400">{s.win_count}</td>
                  <td className="text-right py-3 px-2 text-red-400">{s.loss_count}</td>
                  <td className={`text-right py-3 px-2 font-bold ${s.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {s.win_rate}%
                  </td>
                  <td className={`text-right py-3 px-2 font-bold ${pnlColor(s.total_pnl)}`}>
                    ${s.total_pnl.toFixed(2)}
                  </td>
                  <td className={`text-right py-3 px-2 ${pnlColor(s.avg_profit)}`}>
                    ${s.avg_profit.toFixed(2)}
                  </td>
                  <td className="text-right py-3 px-2 text-green-400">
                    ${s.max_win.toFixed(2)}
                  </td>
                  <td className="text-right py-3 px-2 text-red-400">
                    ${s.max_loss.toFixed(2)}
                  </td>
                  <td className="text-right py-3 px-2 text-gray-300">
                    {s.profit_factor !== null ? s.profit_factor.toFixed(2) : 'N/A'}
                  </td>
                  <td className="text-right py-3 px-2 text-gray-400">
                    {s.avg_holding_hours !== null ? `${s.avg_holding_hours.toFixed(1)}h` : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {data.length === 0 && !loading && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <GitCompareArrows size={48} className="text-gray-700 mx-auto mb-4" />
          <p className="text-gray-500">Aucune donnee de trading pour cette periode</p>
          <p className="text-gray-600 text-sm mt-1">Les comparaisons apparaitront apres vos premiers trades</p>
        </div>
      )}
    </div>
  )
}
