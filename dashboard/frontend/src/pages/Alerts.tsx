import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Bell,
  Trash2,
  Plus,
  Loader2,
  ArrowUp,
  ArrowDown,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react'

interface Alert {
  id: number
  pair: string
  condition: string
  target_price: number
  note: string | null
  active: boolean
  triggered: boolean
  triggered_at: string | null
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

export default function Alerts({ token }: { token: string }) {
  const api = useApi(token)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)

  // Form state
  const [pair, setPair] = useState(PAIRS[0])
  const [condition, setCondition] = useState<'above' | 'below'>('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => {
    loadAlerts()
  }, [token])

  const loadAlerts = async () => {
    setLoading(true)
    try {
      const res = await api.get('/alerts/')
      setAlerts(res.data)
    } catch {
      setMessage({ text: 'Erreur lors du chargement des alertes', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const createAlert = async () => {
    if (!targetPrice || parseFloat(targetPrice) <= 0) {
      setMessage({ text: 'Le prix cible doit être positif', type: 'error' })
      return
    }
    setCreating(true)
    setMessage(null)
    try {
      await api.post('/alerts/', {
        pair,
        condition,
        target_price: parseFloat(targetPrice),
        note: note || null,
      })
      setTargetPrice('')
      setNote('')
      setMessage({ text: 'Alerte créée', type: 'success' })
      await loadAlerts()
    } catch {
      setMessage({ text: 'Erreur lors de la création', type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const deleteAlert = async (id: number) => {
    try {
      await api.delete(`/alerts/${id}`)
      setAlerts((prev) => prev.filter((a) => a.id !== id))
      setMessage({ text: 'Alerte supprimée', type: 'success' })
    } catch {
      setMessage({ text: 'Erreur lors de la suppression', type: 'error' })
    }
  }

  const toggleAlert = async (id: number) => {
    try {
      const res = await api.put(`/alerts/${id}/toggle`)
      setAlerts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, active: res.data.active } : a)),
      )
    } catch {
      setMessage({ text: 'Erreur lors du basculement', type: 'error' })
    }
  }

  const activeAlerts = alerts.filter((a) => !a.triggered)
  const triggeredAlerts = alerts.filter((a) => a.triggered)

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
        <Bell className="text-yellow-400" size={24} />
        <h2 className="text-2xl font-bold">Alertes de Prix</h2>
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
          Nouvelle alerte
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
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

          {/* Condition */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Condition</label>
            <select
              value={condition}
              onChange={(e) => setCondition(e.target.value as 'above' | 'below')}
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            >
              <option value="above">Au-dessus de</option>
              <option value="below">En-dessous de</option>
            </select>
          </div>

          {/* Target price */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Prix cible (USD)
            </label>
            <input
              type="number"
              step="any"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder="0.00"
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>

          {/* Note */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Note (optionnel)
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Raison de l'alerte..."
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>
        </div>

        <button
          onClick={createAlert}
          disabled={creating || !targetPrice}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Créer l'alerte
        </button>
      </div>

      {/* Active alerts */}
      <h3 className="text-lg font-semibold mb-3">
        Alertes actives ({activeAlerts.length})
      </h3>
      {activeAlerts.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center mb-6">
          <Bell size={32} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">Aucune alerte active</p>
          <p className="text-xs text-gray-600 mt-1">
            Créez une alerte pour être notifié quand un prix atteint votre seuil
          </p>
        </div>
      ) : (
        <div className="space-y-3 mb-6">
          {activeAlerts.map((alert) => (
            <div
              key={alert.id}
              className="bg-gray-900 rounded-xl border border-gray-800 p-4 flex items-center gap-4"
            >
              <div
                className={`p-2 rounded-lg ${
                  alert.condition === 'above'
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-red-500/10 text-red-400'
                }`}
              >
                {alert.condition === 'above' ? (
                  <ArrowUp size={20} />
                ) : (
                  <ArrowDown size={20} />
                )}
              </div>

              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{alert.pair}</span>
                  <span className="text-xs text-gray-500">
                    {alert.condition === 'above' ? 'au-dessus de' : 'en-dessous de'}
                  </span>
                  <span className="font-mono text-yellow-400">
                    ${alert.target_price.toLocaleString()}
                  </span>
                </div>
                {alert.note && (
                  <p className="text-xs text-gray-500 mt-1">{alert.note}</p>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => toggleAlert(alert.id)}
                  className="p-1.5 rounded-lg hover:bg-gray-800 transition text-gray-400 hover:text-gray-200"
                  title={alert.active ? 'Désactiver' : 'Activer'}
                >
                  {alert.active ? (
                    <ToggleRight size={22} className="text-green-400" />
                  ) : (
                    <ToggleLeft size={22} className="text-gray-600" />
                  )}
                </button>
                <button
                  onClick={() => deleteAlert(alert.id)}
                  className="p-1.5 rounded-lg hover:bg-gray-800 transition text-gray-400 hover:text-red-400"
                  title="Supprimer"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Triggered alerts */}
      {triggeredAlerts.length > 0 && (
        <>
          <h3 className="text-lg font-semibold mb-3 text-gray-500">
            Alertes déclenchées ({triggeredAlerts.length})
          </h3>
          <div className="space-y-3">
            {triggeredAlerts.map((alert) => (
              <div
                key={alert.id}
                className="bg-gray-900/50 rounded-xl border border-gray-800/50 p-4 flex items-center gap-4 opacity-60"
              >
                <div className="p-2 rounded-lg bg-gray-800 text-gray-500">
                  {alert.condition === 'above' ? (
                    <ArrowUp size={20} />
                  ) : (
                    <ArrowDown size={20} />
                  )}
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-400">
                      {alert.pair}
                    </span>
                    <span className="text-xs text-gray-600">
                      {alert.condition === 'above' ? 'au-dessus de' : 'en-dessous de'}
                    </span>
                    <span className="font-mono text-gray-400">
                      ${alert.target_price.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    {alert.note && (
                      <span className="text-xs text-gray-600">{alert.note}</span>
                    )}
                    {alert.triggered_at && (
                      <span className="text-xs text-gray-600">
                        Déclenché le{' '}
                        {new Date(alert.triggered_at).toLocaleString('fr-FR')}
                      </span>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => deleteAlert(alert.id)}
                  className="p-1.5 rounded-lg hover:bg-gray-800 transition text-gray-500 hover:text-red-400"
                  title="Supprimer"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
