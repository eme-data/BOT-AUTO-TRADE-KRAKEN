import { useEffect, useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  Briefcase,
  Target,
  RefreshCw,
  Loader2,
  Save,
  Play,
  Plus,
  Trash2,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'

/* ── Types ─────────────────────────────────────────── */

interface Holding {
  pair: string
  quantity: number
  current_price: number
  value_usd: number
  allocation_pct: number
}

interface TargetAllocation {
  id?: number
  pair: string
  target_pct: number
}

interface RebalanceTrade {
  pair: string
  current_pct: number
  target_pct: number
  diff_pct: number
  action: 'buy' | 'sell'
  amount_usd: number
}

/* ── Constants ─────────────────────────────────────── */

const COLORS = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#f97316',
  '#14b8a6',
  '#a855f7',
  '#6366f1',
  '#84cc16',
]

const PAIRS = [
  'BTC/USD',
  'ETH/USD',
  'SOL/USD',
  'XRP/USD',
  'ADA/USD',
  'DOT/USD',
  'AVAX/USD',
  'LINK/USD',
  'MATIC/USD',
  'DOGE/USD',
]

/* ── Component ─────────────────────────────────────── */

export default function Portfolio({ token }: { token: string }) {
  const api = useApi(token)

  const [holdings, setHoldings] = useState<Holding[]>([])
  const [totalValue, setTotalValue] = useState(0)
  const [targets, setTargets] = useState<TargetAllocation[]>([])
  const [preview, setPreview] = useState<RebalanceTrade[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [rebalancing, setRebalancing] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)

  // Editable targets (local state for form)
  const [editTargets, setEditTargets] = useState<TargetAllocation[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [holdingsRes, targetsRes] = await Promise.all([
        api.get('/portfolio/holdings'),
        api.get('/portfolio/targets'),
      ])
      setHoldings(holdingsRes.data.holdings || [])
      setTotalValue(holdingsRes.data.total_value || 0)
      const t = targetsRes.data || []
      setTargets(t)
      setEditTargets(
        t.length > 0
          ? t.map((x: TargetAllocation) => ({
              pair: x.pair,
              target_pct: x.target_pct,
            }))
          : [{ pair: PAIRS[0], target_pct: 0 }],
      )
    } catch {
      setMessage({ text: 'Erreur lors du chargement du portfolio', type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    loadData()
  }, [])

  const totalTargetPct = editTargets.reduce((s, t) => s + (t.target_pct || 0), 0)

  const saveTargets = async () => {
    if (totalTargetPct > 100) {
      setMessage({ text: 'Le total des cibles ne peut pas dépasser 100%', type: 'error' })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      await api.put('/portfolio/targets', {
        targets: editTargets.filter((t) => t.target_pct > 0),
      })
      setMessage({ text: 'Cibles sauvegardées', type: 'success' })
      await loadData()
    } catch {
      setMessage({ text: 'Erreur lors de la sauvegarde', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const loadPreview = async () => {
    setPreviewLoading(true)
    try {
      const res = await api.get('/portfolio/rebalance-preview')
      setPreview(res.data.trades || [])
      // total_value available in res.data if needed
    } catch {
      setMessage({
        text: 'Erreur lors du calcul du rebalancement',
        type: 'error',
      })
    } finally {
      setPreviewLoading(false)
    }
  }

  const executeRebalance = async () => {
    if (!confirm('Confirmer le rebalancement du portfolio ?')) return
    setRebalancing(true)
    setMessage(null)
    try {
      const res = await api.post('/portfolio/rebalance')
      const data = res.data
      setMessage({
        text: data.message || 'Rebalancement effectué',
        type: data.errors?.length ? 'error' : 'success',
      })
      setPreview([])
      await loadData()
    } catch (err: any) {
      setMessage({
        text: err.response?.data?.detail || 'Erreur lors du rebalancement',
        type: 'error',
      })
    } finally {
      setRebalancing(false)
    }
  }

  const addTargetRow = () => {
    setEditTargets((prev) => [...prev, { pair: PAIRS[0], target_pct: 0 }])
  }

  const removeTargetRow = (idx: number) => {
    setEditTargets((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateTarget = (idx: number, field: string, value: string | number) => {
    setEditTargets((prev) =>
      prev.map((t, i) => (i === idx ? { ...t, [field]: value } : t)),
    )
  }

  // Pie chart data
  const pieData = holdings
    .filter((h) => h.allocation_pct > 0.5)
    .map((h) => ({
      name: h.pair,
      value: h.allocation_pct,
    }))

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    )
  }

  return (
    <div className="max-w-6xl">
      <div className="flex items-center gap-3 mb-6">
        <Briefcase className="text-blue-400" size={24} />
        <h2 className="text-2xl font-bold">Portfolio</h2>
        <button
          onClick={loadData}
          className="ml-auto p-2 rounded-lg hover:bg-gray-800 transition text-gray-400"
          title="Rafraîchir"
        >
          <RefreshCw size={18} />
        </button>
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

      {/* Overview: Pie chart + total */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Donut chart */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h3 className="text-lg font-semibold mb-4">Répartition</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
                  labelLine={false}
                >
                  {pieData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: '#f3f4f6',
                  }}
                  formatter={(value: number) => [`${value.toFixed(2)}%`, 'Allocation']}
                />
                <Legend
                  wrapperStyle={{ color: '#9ca3af', fontSize: '12px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[280px] text-gray-500">
              Aucune position
            </div>
          )}
        </div>

        {/* Total value card */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h3 className="text-lg font-semibold mb-4">Valeur totale</h3>
          <p className="text-4xl font-bold text-green-400 mb-6">
            ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </p>
          <p className="text-sm text-gray-500">
            {holdings.length} actif{holdings.length !== 1 ? 's' : ''} en portefeuille
          </p>
        </div>
      </div>

      {/* Holdings table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Positions</h3>
        {holdings.length === 0 ? (
          <p className="text-gray-500 text-center py-8">Aucune position</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="text-left py-2 px-3">Paire</th>
                  <th className="text-right py-2 px-3">Quantité</th>
                  <th className="text-right py-2 px-3">Prix</th>
                  <th className="text-right py-2 px-3">Valeur USD</th>
                  <th className="text-right py-2 px-3">Allocation</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <tr
                    key={h.pair}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30"
                  >
                    <td className="py-2 px-3 font-medium">{h.pair}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {h.quantity < 1
                        ? h.quantity.toFixed(8)
                        : h.quantity.toLocaleString('en-US', {
                            maximumFractionDigits: 6,
                          })}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      ${h.current_price.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-green-400">
                      ${h.value_usd.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                      })}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className="px-2 py-0.5 rounded-full text-xs bg-blue-500/10 text-blue-400">
                        {h.allocation_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Target allocations */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Target size={18} className="text-yellow-400" />
          <h3 className="text-lg font-semibold">Allocations cibles</h3>
          <span
            className={`ml-auto text-sm font-mono ${
              totalTargetPct > 100 ? 'text-red-400' : 'text-gray-400'
            }`}
          >
            Total: {totalTargetPct.toFixed(1)}%
          </span>
        </div>

        <div className="space-y-3 mb-4">
          {editTargets.map((t, idx) => (
            <div key={idx} className="flex items-center gap-3">
              <select
                value={t.pair}
                onChange={(e) => updateTarget(idx, 'pair', e.target.value)}
                className="flex-1 px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
              >
                {PAIRS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <div className="relative w-32">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={t.target_pct || ''}
                  onChange={(e) =>
                    updateTarget(idx, 'target_pct', parseFloat(e.target.value) || 0)
                  }
                  className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100 pr-8"
                  placeholder="0"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                  %
                </span>
              </div>
              {/* Progress bar */}
              <div className="w-24 h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{ width: `${Math.min(t.target_pct || 0, 100)}%` }}
                />
              </div>
              <button
                onClick={() => removeTargetRow(idx)}
                className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-red-400 transition"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          <button
            onClick={addTargetRow}
            className="flex items-center gap-1 px-3 py-2 text-sm rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
          >
            <Plus size={14} /> Ajouter
          </button>
          <button
            onClick={saveTargets}
            disabled={saving || totalTargetPct > 100}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Sauvegarder les cibles
          </button>
        </div>
      </div>

      {/* Rebalance preview */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center gap-2 mb-4">
          <RefreshCw size={18} className="text-purple-400" />
          <h3 className="text-lg font-semibold">Rebalancement</h3>
        </div>

        <button
          onClick={loadPreview}
          disabled={previewLoading}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm font-medium transition mb-4 disabled:opacity-50"
        >
          {previewLoading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          Calculer le rebalancement
        </button>

        {preview.length > 0 && (
          <>
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-800">
                    <th className="text-left py-2 px-3">Paire</th>
                    <th className="text-right py-2 px-3">Actuel</th>
                    <th className="text-right py-2 px-3">Cible</th>
                    <th className="text-right py-2 px-3">Action</th>
                    <th className="text-right py-2 px-3">Montant USD</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((t) => (
                    <tr
                      key={t.pair}
                      className="border-b border-gray-800/50 hover:bg-gray-800/30"
                    >
                      <td className="py-2 px-3 font-medium">{t.pair}</td>
                      <td className="py-2 px-3 text-right font-mono text-gray-300">
                        {t.current_pct.toFixed(1)}%
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-gray-300">
                        {t.target_pct.toFixed(1)}%
                      </td>
                      <td className="py-2 px-3 text-right">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            t.action === 'buy'
                              ? 'bg-green-500/10 text-green-400'
                              : 'bg-red-500/10 text-red-400'
                          }`}
                        >
                          {t.action === 'buy' ? (
                            <TrendingUp size={12} />
                          ) : (
                            <TrendingDown size={12} />
                          )}
                          {t.action === 'buy' ? 'Acheter' : 'Vendre'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-yellow-400">
                        ${t.amount_usd.toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button
              onClick={executeRebalance}
              disabled={rebalancing}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
            >
              {rebalancing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              Executer le rebalancement
            </button>
          </>
        )}

        {preview.length === 0 && !previewLoading && targets.length > 0 && (
          <p className="text-gray-500 text-sm">
            Cliquez sur "Calculer" pour voir les trades nécessaires
          </p>
        )}
        {targets.length === 0 && (
          <p className="text-gray-500 text-sm">
            Configurez d'abord vos allocations cibles ci-dessus
          </p>
        )}
      </div>
    </div>
  )
}
