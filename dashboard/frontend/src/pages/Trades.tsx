import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Trade {
  id: number
  order_id: string
  pair: string
  direction: string
  size: number
  entry_price: number
  exit_price: number | null
  profit: number | null
  fee: number
  status: string
  strategy: string
  opened_at: string
  closed_at: string | null
}

interface TradeStats {
  total_trades: number
  winning: number
  losing: number
  total_pnl: number
  total_fees: number
  win_rate: number
  avg_win: number
  avg_loss: number
  best_trade: number
  worst_trade: number
  profit_factor: number | null
}

const DAYS_OPTIONS = [
  { label: '7 days', value: 7 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
  { label: 'All', value: 0 },
]

export default function Trades({ token }: { token: string }) {
  const api = useApi(token)
  const [trades, setTrades] = useState<Trade[]>([])
  const [stats, setStats] = useState<TradeStats | null>(null)
  const [days, setDays] = useState(30)

  useEffect(() => {
    api.get('/trades/?limit=500').then((r) => setTrades(r.data))
    api.get(`/trades/stats?days=${days || ''}`).then((r) => setStats(r.data))
  }, [token, days])

  const handleExport = async (format: 'csv' | 'pdf') => {
    const daysParam = days > 0 ? `days=${days}` : ''
    const res = await fetch(`/api/trades/export/${format}?${daysParam}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trades_${days || 'all'}d.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Trade History</h2>

      {/* Toolbar: days filter + export buttons */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Period:</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-1.5 focus:ring-blue-500 focus:border-blue-500"
          >
            {DAYS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-2 ml-auto">
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm text-gray-200 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Export CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm text-gray-200 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Export PDF
          </button>
        </div>
      </div>

      {/* Stats summary bar */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Total Trades</div>
            <div className="text-lg font-bold">{stats.total_trades}</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Win Rate</div>
            <div className="text-lg font-bold">{stats.win_rate}%</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Total P&L</div>
            <div className={`text-lg font-bold ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              ${stats.total_pnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Won / Lost</div>
            <div className="text-lg font-bold">
              <span className="text-green-400">{stats.winning}</span>
              {' / '}
              <span className="text-red-400">{stats.losing}</span>
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Total Fees</div>
            <div className="text-lg font-bold text-yellow-400">${stats.total_fees.toFixed(2)}</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">Profit Factor</div>
            <div className="text-lg font-bold">
              {stats.profit_factor !== null ? stats.profit_factor.toFixed(2) : 'N/A'}
            </div>
          </div>
        </div>
      )}

      {/* Trade table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 bg-gray-800/50">
              <th className="text-left px-4 py-3">Date</th>
              <th className="text-left px-4 py-3">Pair</th>
              <th className="text-left px-4 py-3">Direction</th>
              <th className="text-right px-4 py-3">Size</th>
              <th className="text-right px-4 py-3">Entry</th>
              <th className="text-right px-4 py-3">Exit</th>
              <th className="text-right px-4 py-3">P&L</th>
              <th className="text-left px-4 py-3">Strategy</th>
              <th className="text-left px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-t border-gray-800/50 hover:bg-gray-800/30">
                <td className="px-4 py-2 text-gray-400 text-xs">
                  {new Date(t.opened_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 font-mono">{t.pair}</td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      t.direction === 'buy'
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {t.direction.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-2 text-right font-mono">{t.size}</td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.entry_price.toFixed(2)}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.exit_price ? t.exit_price.toFixed(2) : '-'}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.profit != null ? (
                    <span
                      className={
                        t.profit >= 0 ? 'text-green-400' : 'text-red-400'
                      }
                    >
                      ${t.profit.toFixed(2)}
                    </span>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="px-4 py-2 text-gray-400 text-xs">{t.strategy}</td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      t.status === 'OPEN'
                        ? 'bg-blue-500/20 text-blue-400'
                        : t.status === 'SHADOW'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-gray-700 text-gray-400'
                    }`}
                  >
                    {t.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
