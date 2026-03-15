import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { FlaskConical, TrendingUp, BarChart3, Loader2, AlertTriangle } from 'lucide-react'

const COMMON_PAIRS = [
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD',
  'DOT/USD', 'AVAX/USD', 'LINK/USD', 'MATIC/USD', 'ATOM/USD',
  'DOGE/USD', 'LTC/USD',
]

const PERIOD_OPTIONS = [
  { label: '30 jours', value: 30 },
  { label: '60 jours', value: 60 },
  { label: '90 jours', value: 90 },
  { label: '180 jours', value: 180 },
  { label: '365 jours', value: 365 },
]

interface EquityPoint { date: string; equity: number }
interface BacktestTrade {
  date: string; pair: string; direction: string
  entry_price: number; exit_price: number; profit: number; duration_hours: number
}
interface Summary {
  total_pnl: number; win_rate: number; profit_factor: number | null
  max_drawdown: number; sharpe_ratio: number | null; total_trades: number; avg_profit: number
}
interface StrategyInfo { name: string; display_name: string }

export default function Backtest({ token }: { token: string }) {
  const api = useApi(token)

  // Form state
  const [pair, setPair] = useState('BTC/USD')
  const [strategy, setStrategy] = useState('')
  const [days, setDays] = useState(90)
  const [capital, setCapital] = useState(10000)

  // Strategies list
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [strategiesLoaded, setStrategiesLoaded] = useState(false)

  // Results
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([])
  const [trades, setTrades] = useState<BacktestTrade[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [hasResults, setHasResults] = useState(false)

  // Load strategies on first render
  if (!strategiesLoaded) {
    setStrategiesLoaded(true)
    api.get('/backtest/strategies').then(res => {
      setStrategies(res.data)
      if (res.data.length > 0 && !strategy) {
        setStrategy(res.data[0].name)
      }
    }).catch(() => { /* ignore */ })
  }

  const runBacktest = async () => {
    if (!strategy) return
    setLoading(true)
    setError(null)
    setHasResults(false)
    try {
      const res = await api.post('/backtest/run', {
        pair,
        strategy,
        days,
        initial_capital: capital,
      })
      setEquityCurve(res.data.equity_curve)
      setTrades(res.data.trades)
      setSummary(res.data.summary)
      setHasResults(true)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Erreur inconnue'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color || 'text-white'}`}>{value}</p>
    </div>
  )

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FlaskConical size={24} className="text-purple-400" />
        <h2 className="text-2xl font-bold">Backtest</h2>
      </div>

      {/* Form */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Pair */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Paire</label>
            <select
              value={pair}
              onChange={e => setPair(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-purple-500 focus:outline-none"
            >
              {COMMON_PAIRS.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          {/* Strategy */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Strategie</label>
            <select
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-purple-500 focus:outline-none"
            >
              {strategies.map(s => (
                <option key={s.name} value={s.name}>{s.display_name}</option>
              ))}
            </select>
          </div>

          {/* Period */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Periode</label>
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-purple-500 focus:outline-none"
            >
              {PERIOD_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Capital */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Capital initial ($)</label>
            <input
              type="number"
              value={capital}
              onChange={e => setCapital(Number(e.target.value))}
              min={100}
              step={100}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-purple-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-4 flex items-center gap-4">
          <button
            onClick={runBacktest}
            disabled={loading || !strategy}
            className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-sm transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Simulation en cours...
              </>
            ) : (
              <>
                <FlaskConical size={16} />
                Lancer le backtest
              </>
            )}
          </button>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {hasResults && summary && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <Stat
              label="P&L Total"
              value={`$${summary.total_pnl.toFixed(2)}`}
              color={summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}
            />
            <Stat
              label="Win Rate"
              value={`${summary.win_rate.toFixed(1)}%`}
              color={summary.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'}
            />
            <Stat
              label="Max Drawdown"
              value={`${summary.max_drawdown.toFixed(1)}%`}
              color="text-red-400"
            />
            <Stat
              label="Sharpe Ratio"
              value={summary.sharpe_ratio !== null ? summary.sharpe_ratio.toFixed(2) : 'N/A'}
              color={summary.sharpe_ratio !== null && summary.sharpe_ratio > 1 ? 'text-green-400' : 'text-gray-300'}
            />
            <Stat
              label="Profit Factor"
              value={summary.profit_factor !== null ? summary.profit_factor.toFixed(2) : 'N/A'}
              color={summary.profit_factor !== null && summary.profit_factor > 1 ? 'text-green-400' : 'text-gray-300'}
            />
            <Stat
              label="Total Trades"
              value={String(summary.total_trades)}
            />
            <Stat
              label="Profit moyen"
              value={`$${summary.avg_profit.toFixed(2)}`}
              color={summary.avg_profit >= 0 ? 'text-green-400' : 'text-red-400'}
            />
          </div>

          {/* Equity Curve */}
          {equityCurve.length > 1 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={18} className="text-purple-400" />
                <h3 className="font-semibold">Courbe d'equity</h3>
              </div>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={equityCurve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    tickFormatter={(v: string) => v.slice(5)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    tickFormatter={(v: number) => `$${v.toLocaleString()}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2937',
                      border: '1px solid #374151',
                      borderRadius: 8,
                    }}
                    formatter={(value: number) => [`$${value.toLocaleString()}`, 'Equity']}
                    labelFormatter={(label: string) => `Date: ${label}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="equity"
                    stroke="#a855f7"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: '#a855f7' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trade list */}
          {trades.length > 0 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <BarChart3 size={18} className="text-purple-400" />
                  <h3 className="font-semibold">Liste des trades ({trades.length})</h3>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-500 text-xs border-b border-gray-800">
                      <th className="text-left py-2 px-3">Date</th>
                      <th className="text-left py-2 px-3">Paire</th>
                      <th className="text-left py-2 px-3">Direction</th>
                      <th className="text-right py-2 px-3">Prix entree</th>
                      <th className="text-right py-2 px-3">Prix sortie</th>
                      <th className="text-right py-2 px-3">Profit</th>
                      <th className="text-right py-2 px-3">Duree (h)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                        <td className="py-2 px-3 text-gray-400">{t.date}</td>
                        <td className="py-2 px-3 font-medium">{t.pair}</td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            t.direction === 'buy'
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-red-500/20 text-red-400'
                          }`}>
                            {t.direction.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-gray-300">
                          ${t.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-gray-300">
                          ${t.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                        </td>
                        <td className={`py-2 px-3 text-right font-bold ${
                          t.profit >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {t.profit >= 0 ? '+' : ''}{t.profit.toFixed(2)}$
                        </td>
                        <td className="py-2 px-3 text-right text-gray-400">
                          {t.duration_hours.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* No trades */}
          {trades.length === 0 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
              <AlertTriangle size={48} className="text-yellow-500 mx-auto mb-4" />
              <p className="text-gray-400">Aucun trade genere durant cette periode</p>
              <p className="text-gray-600 text-sm mt-1">
                La strategie n'a pas produit de signaux exploitables sur les donnees historiques
              </p>
            </div>
          )}
        </>
      )}

      {/* Initial empty state */}
      {!hasResults && !loading && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <FlaskConical size={48} className="text-gray-700 mx-auto mb-4" />
          <p className="text-gray-500">Configurez les parametres et lancez un backtest</p>
          <p className="text-gray-600 text-sm mt-1">
            Testez vos strategies sur des donnees historiques avant de trader en reel
          </p>
        </div>
      )}
    </div>
  )
}
