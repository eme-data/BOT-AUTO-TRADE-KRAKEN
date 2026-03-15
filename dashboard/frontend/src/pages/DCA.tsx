import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  RefreshCw,
  Trash2,
  Plus,
  Loader2,
  ToggleLeft,
  ToggleRight,
  DollarSign,
  Calendar,
} from 'lucide-react'

interface DCASchedule {
  id: number
  pair: string
  amount_usd: number
  frequency: string
  active: boolean
  next_run: string | null
  last_run: string | null
  total_invested: number
  total_bought: number
  executions: number
  created_at: string | null
}

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

const FREQUENCIES: { value: string; label: string }[] = [
  { value: 'daily', label: 'Quotidien' },
  { value: 'weekly', label: 'Hebdo' },
  { value: 'biweekly', label: 'Bi-mensuel' },
  { value: 'monthly', label: 'Mensuel' },
]

const freqLabel = (f: string) =>
  FREQUENCIES.find((fr) => fr.value === f)?.label || f

export default function DCA({ token }: { token: string }) {
  const api = useApi(token)
  const [schedules, setSchedules] = useState<DCASchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)

  // Form state
  const [pair, setPair] = useState(PAIRS[0])
  const [amountUsd, setAmountUsd] = useState('')
  const [frequency, setFrequency] = useState('weekly')

  useEffect(() => {
    loadSchedules()
  }, [token])

  const loadSchedules = async () => {
    setLoading(true)
    try {
      const res = await api.get('/dca/')
      setSchedules(res.data)
    } catch {
      setMessage({
        text: 'Erreur lors du chargement des planifications DCA',
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  const createSchedule = async () => {
    if (!amountUsd || parseFloat(amountUsd) <= 0) {
      setMessage({ text: 'Le montant doit être positif', type: 'error' })
      return
    }
    setCreating(true)
    setMessage(null)
    try {
      await api.post('/dca/', {
        pair,
        amount_usd: parseFloat(amountUsd),
        frequency,
      })
      setAmountUsd('')
      setMessage({ text: 'Planification DCA créée', type: 'success' })
      await loadSchedules()
    } catch {
      setMessage({ text: 'Erreur lors de la création', type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const deleteSchedule = async (id: number) => {
    try {
      await api.delete(`/dca/${id}`)
      setSchedules((prev) => prev.filter((s) => s.id !== id))
      setMessage({ text: 'Planification supprimée', type: 'success' })
    } catch {
      setMessage({ text: 'Erreur lors de la suppression', type: 'error' })
    }
  }

  const toggleSchedule = async (id: number) => {
    try {
      const res = await api.put(`/dca/${id}/toggle`)
      setSchedules((prev) =>
        prev.map((s) =>
          s.id === id ? { ...s, active: res.data.active } : s,
        ),
      )
    } catch {
      setMessage({ text: 'Erreur lors du basculement', type: 'error' })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center gap-3 mb-6">
        <RefreshCw className="text-blue-400" size={24} />
        <h2 className="text-2xl font-bold">DCA (Dollar Cost Averaging)</h2>
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

      {/* Create form */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Plus size={18} className="text-blue-400" />
          Nouvelle planification DCA
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {/* Pair */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Paire</label>
            <select
              value={pair}
              onChange={(e) => setPair(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            >
              {PAIRS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          {/* Amount */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Montant (USD)
            </label>
            <input
              type="number"
              step="any"
              min="0"
              value={amountUsd}
              onChange={(e) => setAmountUsd(e.target.value)}
              placeholder="50.00"
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>

          {/* Frequency */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Fréquence
            </label>
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            >
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={createSchedule}
          disabled={creating || !amountUsd}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          {creating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Plus size={14} />
          )}
          Créer la planification
        </button>
      </div>

      {/* Schedules list */}
      <h3 className="text-lg font-semibold mb-3">
        Planifications ({schedules.length})
      </h3>
      {schedules.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center">
          <RefreshCw size={32} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">Aucune planification DCA</p>
          <p className="text-xs text-gray-600 mt-1">
            Le DCA permet d'investir automatiquement à intervalles réguliers
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map((sched) => (
            <div
              key={sched.id}
              className={`bg-gray-900 rounded-xl border border-gray-800 p-4 ${
                !sched.active ? 'opacity-50' : ''
              }`}
            >
              <div className="flex items-center gap-4 mb-3">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
                  <DollarSign size={20} />
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{sched.pair}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-400">
                      {freqLabel(sched.frequency)}
                    </span>
                    <span className="font-mono text-green-400">
                      ${sched.amount_usd.toFixed(2)}
                    </span>
                  </div>
                  {sched.next_run && (
                    <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                      <Calendar size={12} />
                      Prochain achat :{' '}
                      {new Date(sched.next_run).toLocaleString('fr-FR')}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleSchedule(sched.id)}
                    className="p-1.5 rounded-lg hover:bg-gray-800 transition text-gray-400 hover:text-gray-200"
                    title={sched.active ? 'Désactiver' : 'Activer'}
                  >
                    {sched.active ? (
                      <ToggleRight size={22} className="text-green-400" />
                    ) : (
                      <ToggleLeft size={22} className="text-gray-600" />
                    )}
                  </button>
                  <button
                    onClick={() => deleteSchedule(sched.id)}
                    className="p-1.5 rounded-lg hover:bg-gray-800 transition text-gray-400 hover:text-red-400"
                    title="Supprimer"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              {/* Stats */}
              {sched.executions > 0 && (
                <div className="grid grid-cols-3 gap-3 pt-3 border-t border-gray-800">
                  <div className="text-center">
                    <p className="text-xs text-gray-500">Total investi</p>
                    <p className="font-mono text-sm text-gray-200">
                      ${sched.total_invested.toFixed(2)}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-500">Total acheté</p>
                    <p className="font-mono text-sm text-gray-200">
                      {sched.total_bought.toFixed(6)}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-500">Exécutions</p>
                    <p className="font-mono text-sm text-gray-200">
                      {sched.executions}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
