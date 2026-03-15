import { useEffect, useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import {
  FileText, Loader2, RefreshCw, Bell, TrendingUp, TrendingDown,
  Award, AlertTriangle, BarChart3,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

/* -- Types -------------------------------------------------- */

interface TradeInfo {
  pair: string
  profit: number
  direction: string
  opened_at: string | null
}

interface DailyReport {
  period: string
  date?: string
  total_trades: number
  total_pnl: number
  win_rate: number
  winning: number
  losing: number
  best_trade: TradeInfo | null
  worst_trade: TradeInfo | null
  total_fees: number
}

interface DayBreakdown {
  date: string
  pnl: number
  trades: number
  wins: number
}

interface WeeklyReport extends DailyReport {
  from: string
  to: string
  daily_breakdown: DayBreakdown[]
}

/* -- Component ----------------------------------------------- */

export default function Reports({ token }: { token: string }) {
  const api = useApi(token)

  const [tab, setTab] = useState<'daily' | 'weekly'>('daily')
  const [loading, setLoading] = useState(true)
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null)
  const [weeklyReport, setWeeklyReport] = useState<WeeklyReport | null>(null)
  const [sending, setSending] = useState(false)
  const [sendResult, setSendResult] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  const loadReport = useCallback(async (period: 'daily' | 'weekly') => {
    setLoading(true)
    try {
      const res = await api.get(`/reports/${period}`)
      if (period === 'daily') setDailyReport(res.data)
      else setWeeklyReport(res.data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { loadReport(tab) }, [tab])

  // Auto-refresh every 60s
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => loadReport(tab), 60_000)
    return () => clearInterval(interval)
  }, [autoRefresh, tab, loadReport])

  const handleSendNow = async () => {
    setSending(true)
    setSendResult(null)
    try {
      const res = await api.post('/reports/send-now')
      setSendResult(`Notification envoyee (${res.data.sent} appareil${res.data.sent > 1 ? 's' : ''})`)
    } catch {
      setSendResult('Erreur lors de l\'envoi')
    } finally {
      setSending(false)
    }
  }

  const report = tab === 'daily' ? dailyReport : weeklyReport

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
          <FileText size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Rapports</h2>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
              className="rounded bg-gray-800 border-gray-700"
            />
            Auto-refresh
          </label>
          <button
            onClick={() => loadReport(tab)}
            className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 text-sm transition"
          >
            <RefreshCw size={14} />
            Rafraichir
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <button
          onClick={() => setTab('daily')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
            tab === 'daily'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          Quotidien
        </button>
        <button
          onClick={() => setTab('weekly')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
            tab === 'weekly'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          Hebdomadaire
        </button>
      </div>

      {/* Send notification button */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={handleSendNow}
          disabled={sending}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          <Bell size={16} />
          {sending ? 'Envoi...' : 'Envoyer par notification'}
        </button>
        {sendResult && (
          <span className="text-sm text-gray-400">{sendResult}</span>
        )}
      </div>

      {report ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Total P&L */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                {report.total_pnl >= 0 ? (
                  <TrendingUp size={16} className="text-green-400" />
                ) : (
                  <TrendingDown size={16} className="text-red-400" />
                )}
                <span className="text-xs text-gray-400 uppercase">P&L Total</span>
              </div>
              <p className={`text-2xl font-bold ${report.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {report.total_pnl >= 0 ? '+' : ''}{report.total_pnl.toFixed(2)} $
              </p>
            </div>

            {/* Trades count */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <BarChart3 size={16} className="text-blue-400" />
                <span className="text-xs text-gray-400 uppercase">Trades</span>
              </div>
              <p className="text-2xl font-bold text-gray-200">{report.total_trades}</p>
              <p className="text-xs text-gray-500 mt-1">
                {report.winning} gagnants / {report.losing} perdants
              </p>
            </div>

            {/* Win rate */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Award size={16} className="text-yellow-400" />
                <span className="text-xs text-gray-400 uppercase">Win Rate</span>
              </div>
              <p className="text-2xl font-bold text-gray-200">{report.win_rate}%</p>
              <div className="w-full bg-gray-700 rounded-full h-1.5 mt-2">
                <div
                  className="bg-yellow-500 h-1.5 rounded-full"
                  style={{ width: `${Math.min(report.win_rate, 100)}%` }}
                />
              </div>
            </div>

            {/* Best trade */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={16} className="text-green-400" />
                <span className="text-xs text-gray-400 uppercase">Meilleur trade</span>
              </div>
              {report.best_trade ? (
                <>
                  <p className="text-2xl font-bold text-green-400">+{report.best_trade.profit.toFixed(2)} $</p>
                  <p className="text-xs text-gray-500 mt-1">{report.best_trade.pair} ({report.best_trade.direction})</p>
                </>
              ) : (
                <p className="text-gray-500 text-sm">--</p>
              )}
            </div>

            {/* Worst trade */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={16} className="text-red-400" />
                <span className="text-xs text-gray-400 uppercase">Pire trade</span>
              </div>
              {report.worst_trade ? (
                <>
                  <p className="text-2xl font-bold text-red-400">{report.worst_trade.profit.toFixed(2)} $</p>
                  <p className="text-xs text-gray-500 mt-1">{report.worst_trade.pair} ({report.worst_trade.direction})</p>
                </>
              ) : (
                <p className="text-gray-500 text-sm">--</p>
              )}
            </div>
          </div>

          {/* Weekly bar chart */}
          {tab === 'weekly' && weeklyReport?.daily_breakdown && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={18} className="text-blue-400" />
                <h3 className="font-semibold text-lg">P&L par jour</h3>
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={weeklyReport.daily_breakdown}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#9ca3af', fontSize: 12 }}
                    tickFormatter={(v: string) => {
                      const d = new Date(v + 'T00:00:00')
                      return d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric' })
                    }}
                  />
                  <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2937',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#e5e7eb',
                    }}
                    formatter={(value: number) => [`${value.toFixed(2)} $`, 'P&L']}
                    labelFormatter={(label: string) => {
                      const d = new Date(label + 'T00:00:00')
                      return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'short' })
                    }}
                  />
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {weeklyReport.daily_breakdown.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>

              {/* Day-by-day detail table */}
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-gray-800">
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4 text-right">P&L</th>
                      <th className="pb-2 pr-4 text-right">Trades</th>
                      <th className="pb-2 text-right">Gagnants</th>
                    </tr>
                  </thead>
                  <tbody>
                    {weeklyReport.daily_breakdown.map(day => (
                      <tr key={day.date} className="border-b border-gray-800/50">
                        <td className="py-2 pr-4 text-gray-300">
                          {new Date(day.date + 'T00:00:00').toLocaleDateString('fr-FR', {
                            weekday: 'short',
                            day: 'numeric',
                            month: 'short',
                          })}
                        </td>
                        <td className={`py-2 pr-4 text-right font-medium ${day.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {day.pnl >= 0 ? '+' : ''}{day.pnl.toFixed(2)} $
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-300">{day.trades}</td>
                        <td className="py-2 text-right text-gray-300">{day.wins}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Fees info */}
          {report.total_fees > 0 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-sm text-gray-400">
                Frais totaux: <span className="text-gray-200 font-medium">{report.total_fees.toFixed(2)} $</span>
              </p>
            </div>
          )}
        </>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <FileText size={48} className="text-gray-700 mx-auto mb-4" />
          <p className="text-gray-500">Aucun rapport disponible</p>
        </div>
      )}
    </div>
  )
}
