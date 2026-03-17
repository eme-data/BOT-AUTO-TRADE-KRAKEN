import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Target,
  TrendingUp,
  DollarSign,
  BarChart3,
  Save,
  Loader2,
  Trophy,
  Calendar,
  Percent,
  Hash,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface TargetData {
  target: number
  current: number
  progress_pct: number
  reached: boolean
  trades: number
  fees: number
  net_pnl: number
}

interface TargetStatus {
  daily: TargetData
  weekly: TargetData
}

interface DailyFee {
  date: string
  fees: number
  pnl: number
  trades: number
  fee_pct_of_pnl: number
}

interface PairFee {
  pair: string
  fees: number
  pnl: number
  trades: number
  avg_fee: number
}

interface FeeSummary {
  period_days: number
  total_fees: number
  total_pnl: number
  net_pnl: number
  fee_pct_of_pnl: number
  total_trades: number
  avg_fee_per_trade: number
  daily: DailyFee[]
  by_pair: PairFee[]
}

const PERIODS = [
  { label: '7j', value: 7 },
  { label: '14j', value: 14 },
  { label: '30j', value: 30 },
  { label: '90j', value: 90 },
]

export default function Targets({ token }: { token: string }) {
  const api = useApi(token)
  const [targets, setTargets] = useState<TargetStatus | null>(null)
  const [fees, setFees] = useState<FeeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [feePeriod, setFeePeriod] = useState(30)
  const [editDaily, setEditDaily] = useState('')
  const [editWeekly, setEditWeekly] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)

  useEffect(() => {
    loadTargets()
  }, [token])

  useEffect(() => {
    loadFees()
  }, [token, feePeriod])

  const loadTargets = async () => {
    setLoading(true)
    try {
      const res = await api.get('/targets/status')
      setTargets(res.data)
      setEditDaily(String(res.data.daily.target))
      setEditWeekly(String(res.data.weekly.target))
    } catch {
      setMessage({
        text: 'Erreur lors du chargement des objectifs',
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  const loadFees = async () => {
    try {
      const res = await api.get(`/fees/summary?days=${feePeriod}`)
      setFees(res.data)
    } catch {
      // silent
    }
  }

  const saveTargets = async () => {
    const daily = parseFloat(editDaily)
    const weekly = parseFloat(editWeekly)
    if (isNaN(daily) || isNaN(weekly) || daily <= 0 || weekly <= 0) {
      setMessage({
        text: 'Les objectifs doivent etre des nombres positifs',
        type: 'error',
      })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      await api.put(`/targets/configure?daily=${daily}&weekly=${weekly}`)
      setMessage({ text: 'Objectifs mis a jour', type: 'success' })
      await loadTargets()
    } catch {
      setMessage({
        text: 'Erreur lors de la sauvegarde',
        type: 'error',
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    )
  }

  const progressBarColor = (data: TargetData) =>
    data.reached ? 'bg-green-500' : 'bg-blue-500'

  const progressPct = (data: TargetData) =>
    Math.min(Math.max(data.progress_pct, 0), 100)

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Target className="text-yellow-400" size={24} />
        <h2 className="text-2xl font-bold">Objectifs & Frais</h2>
      </div>

      {/* Message */}
      {message && (
        <div
          className={`rounded-lg px-4 py-2 mb-4 text-sm ${
            message.type === 'success'
              ? 'bg-green-500/10 text-green-400'
              : 'bg-red-500/10 text-red-400'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* ═══════ SECTION 1: Profit Targets ═══════ */}
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <TrendingUp size={18} className="text-green-400" />
        Objectifs de Profit
      </h3>

      {targets && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Daily Target Card */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-blue-400" />
                <span className="text-sm font-medium text-gray-300">
                  Objectif Quotidien
                </span>
              </div>
              {targets.daily.reached && (
                <span className="flex items-center gap-1 text-xs font-bold text-green-400 bg-green-500/10 px-2 py-1 rounded-full">
                  <Trophy size={12} />
                  ATTEINT !
                </span>
              )}
            </div>

            <div className="flex items-end gap-2 mb-2">
              <span
                className={`text-2xl font-bold ${
                  targets.daily.reached ? 'text-green-400' : 'text-white'
                }`}
              >
                ${targets.daily.current.toFixed(2)}
              </span>
              <span className="text-sm text-gray-500 mb-0.5">
                / ${targets.daily.target.toFixed(2)}
              </span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-800 rounded-full h-3 mb-3">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${progressBarColor(
                  targets.daily,
                )}`}
                style={{ width: `${progressPct(targets.daily)}%` }}
              />
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs text-gray-400">
              <div>
                <span className="block text-gray-500">Progression</span>
                <span className="font-mono">
                  {targets.daily.progress_pct.toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="block text-gray-500">Trades</span>
                <span className="font-mono">{targets.daily.trades}</span>
              </div>
              <div>
                <span className="block text-gray-500">Frais</span>
                <span className="font-mono text-red-400">
                  -${targets.daily.fees.toFixed(2)}
                </span>
              </div>
            </div>

            <div className="mt-2 pt-2 border-t border-gray-800 text-xs">
              <span className="text-gray-500">P&L net (apres frais) : </span>
              <span
                className={`font-mono font-semibold ${
                  targets.daily.net_pnl >= 0
                    ? 'text-green-400'
                    : 'text-red-400'
                }`}
              >
                ${targets.daily.net_pnl.toFixed(2)}
              </span>
            </div>

            {targets.daily.reached && (
              <div className="mt-3 text-center text-sm text-green-400 font-semibold animate-pulse">
                Objectif quotidien atteint ! Bravo !
              </div>
            )}
          </div>

          {/* Weekly Target Card */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-purple-400" />
                <span className="text-sm font-medium text-gray-300">
                  Objectif Hebdomadaire
                </span>
              </div>
              {targets.weekly.reached && (
                <span className="flex items-center gap-1 text-xs font-bold text-green-400 bg-green-500/10 px-2 py-1 rounded-full">
                  <Trophy size={12} />
                  ATTEINT !
                </span>
              )}
            </div>

            <div className="flex items-end gap-2 mb-2">
              <span
                className={`text-2xl font-bold ${
                  targets.weekly.reached ? 'text-green-400' : 'text-white'
                }`}
              >
                ${targets.weekly.current.toFixed(2)}
              </span>
              <span className="text-sm text-gray-500 mb-0.5">
                / ${targets.weekly.target.toFixed(2)}
              </span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-800 rounded-full h-3 mb-3">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${progressBarColor(
                  targets.weekly,
                )}`}
                style={{ width: `${progressPct(targets.weekly)}%` }}
              />
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs text-gray-400">
              <div>
                <span className="block text-gray-500">Progression</span>
                <span className="font-mono">
                  {targets.weekly.progress_pct.toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="block text-gray-500">Trades</span>
                <span className="font-mono">{targets.weekly.trades}</span>
              </div>
              <div>
                <span className="block text-gray-500">Frais</span>
                <span className="font-mono text-red-400">
                  -${targets.weekly.fees.toFixed(2)}
                </span>
              </div>
            </div>

            <div className="mt-2 pt-2 border-t border-gray-800 text-xs">
              <span className="text-gray-500">P&L net (apres frais) : </span>
              <span
                className={`font-mono font-semibold ${
                  targets.weekly.net_pnl >= 0
                    ? 'text-green-400'
                    : 'text-red-400'
                }`}
              >
                ${targets.weekly.net_pnl.toFixed(2)}
              </span>
            </div>

            {targets.weekly.reached && (
              <div className="mt-3 text-center text-sm text-green-400 font-semibold animate-pulse">
                Objectif hebdomadaire atteint ! Excellente semaine !
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit targets */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-8">
        <h4 className="text-sm font-semibold text-gray-300 mb-4">
          Configurer les objectifs
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Objectif quotidien ($)
            </label>
            <input
              type="number"
              step="any"
              min="0"
              value={editDaily}
              onChange={(e) => setEditDaily(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Objectif hebdomadaire ($)
            </label>
            <input
              type="number"
              step="any"
              min="0"
              value={editWeekly}
              onChange={(e) => setEditWeekly(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>
        </div>
        <button
          onClick={saveTargets}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          {saving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Save size={14} />
          )}
          Enregistrer
        </button>
      </div>

      {/* ═══════ SECTION 2: Fee Analysis ═══════ */}
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <DollarSign size={18} className="text-yellow-400" />
        Analyse des Frais
      </h3>

      {/* Period selector */}
      <div className="flex gap-2 mb-4">
        {PERIODS.map((p) => (
          <button
            key={p.value}
            onClick={() => setFeePeriod(p.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              feePeriod === p.value
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {fees && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-1">
                <DollarSign size={14} className="text-red-400" />
                <span className="text-xs text-gray-500">Total Frais</span>
              </div>
              <span className="text-lg font-bold text-red-400">
                -${fees.total_fees.toFixed(4)}
              </span>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-1">
                <TrendingUp size={14} className="text-green-400" />
                <span className="text-xs text-gray-500">
                  P&L Net (apres frais)
                </span>
              </div>
              <span
                className={`text-lg font-bold ${
                  fees.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                }`}
              >
                ${fees.net_pnl.toFixed(2)}
              </span>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Percent size={14} className="text-yellow-400" />
                <span className="text-xs text-gray-500">Frais % du P&L</span>
              </div>
              <span className="text-lg font-bold text-yellow-400">
                {fees.fee_pct_of_pnl.toFixed(1)}%
              </span>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Hash size={14} className="text-blue-400" />
                <span className="text-xs text-gray-500">
                  Frais Moy. / Trade
                </span>
              </div>
              <span className="text-lg font-bold text-blue-400">
                ${fees.avg_fee_per_trade.toFixed(4)}
              </span>
            </div>
          </div>

          {/* Bar chart: daily fees vs P&L */}
          {fees.daily.length > 0 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
              <h4 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
                <BarChart3 size={16} className="text-blue-400" />
                Frais vs P&L par jour
              </h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={fees.daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    tickFormatter={(v: string) => {
                      const d = new Date(v)
                      return `${d.getDate()}/${d.getMonth() + 1}`
                    }}
                  />
                  <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1F2937',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#E5E7EB',
                      fontSize: 12,
                    }}
                    formatter={(value: number, name: string) => [
                      `$${value.toFixed(4)}`,
                      name === 'fees' ? 'Frais' : 'P&L',
                    ]}
                    labelFormatter={(label: string) => {
                      const d = new Date(label)
                      return d.toLocaleDateString('fr-FR')
                    }}
                  />
                  <Legend
                    formatter={(value: string) =>
                      value === 'fees' ? 'Frais' : 'P&L'
                    }
                  />
                  <Bar dataKey="pnl" fill="#22C55E" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="fees" fill="#EF4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Table by pair */}
          {fees.by_pair.length > 0 && (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h4 className="text-sm font-semibold text-gray-300 mb-4">
                Frais par paire
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500 text-xs">
                      <th className="text-left py-2 pr-4">Paire</th>
                      <th className="text-right py-2 px-4">Total Frais</th>
                      <th className="text-right py-2 px-4">Total P&L</th>
                      <th className="text-right py-2 px-4">Trades</th>
                      <th className="text-right py-2 pl-4">Frais Moy.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fees.by_pair.map((row) => (
                      <tr
                        key={row.pair}
                        className="border-b border-gray-800/50 hover:bg-gray-800/30"
                      >
                        <td className="py-2 pr-4 font-medium">{row.pair}</td>
                        <td className="py-2 px-4 text-right font-mono text-red-400">
                          -${row.fees.toFixed(4)}
                        </td>
                        <td
                          className={`py-2 px-4 text-right font-mono ${
                            row.pnl >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}
                        >
                          ${row.pnl.toFixed(2)}
                        </td>
                        <td className="py-2 px-4 text-right font-mono text-gray-400">
                          {row.trades}
                        </td>
                        <td className="py-2 pl-4 text-right font-mono text-gray-400">
                          ${row.avg_fee.toFixed(4)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
