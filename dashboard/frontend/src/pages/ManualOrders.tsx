import { useEffect, useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import {
  ShoppingCart,
  Loader2,
  RefreshCw,
  Trash2,
  TrendingUp,
  TrendingDown,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react'

/* ── Types ─────────────────────────────────────────── */

interface ManualOrder {
  id: number
  pair: string
  direction: string
  order_type: string
  size: number
  price: number | null
  stop_price: number | null
  status: string
  order_id: string | null
  fill_price: number | null
  fee: number
  created_at: string | null
  filled_at: string | null
}

/* ── Constants ─────────────────────────────────────── */

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

type OrderTypeTab = 'market' | 'limit' | 'stop_limit'

/* ── Component ─────────────────────────────────────── */

export default function ManualOrders({ token }: { token: string }) {
  const api = useApi(token)

  const [orders, setOrders] = useState<ManualOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)

  // Form state
  const [pair, setPair] = useState(PAIRS[0])
  const [direction, setDirection] = useState<'buy' | 'sell'>('buy')
  const [orderType, setOrderType] = useState<OrderTypeTab>('market')
  const [size, setSize] = useState('')
  const [price, setPrice] = useState('')
  const [stopPrice, setStopPrice] = useState('')

  const loadOrders = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/orders/')
      setOrders(res.data)
    } catch {
      setMessage({ text: 'Erreur lors du chargement des ordres', type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    loadOrders()
  }, [])

  const submitOrder = async () => {
    if (!size || parseFloat(size) <= 0) {
      setMessage({ text: 'La taille doit être positive', type: 'error' })
      return
    }
    if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) {
      setMessage({ text: 'Le prix est requis pour un ordre limit', type: 'error' })
      return
    }
    if (orderType === 'stop_limit') {
      if (!price || !stopPrice || parseFloat(price) <= 0 || parseFloat(stopPrice) <= 0) {
        setMessage({
          text: 'Le prix et le stop price sont requis pour un ordre stop-limit',
          type: 'error',
        })
        return
      }
    }

    setSubmitting(true)
    setMessage(null)
    try {
      const body: Record<string, unknown> = {
        pair,
        direction,
        order_type: orderType,
        size: parseFloat(size),
      }
      if (orderType !== 'market' && price) body.price = parseFloat(price)
      if (orderType === 'stop_limit' && stopPrice)
        body.stop_price = parseFloat(stopPrice)

      await api.post('/orders/', body)
      setMessage({
        text:
          orderType === 'market'
            ? 'Ordre market exécuté'
            : 'Ordre placé (en attente)',
        type: 'success',
      })
      setSize('')
      setPrice('')
      setStopPrice('')
      await loadOrders()
    } catch (err: any) {
      setMessage({
        text: err.response?.data?.detail || "Erreur lors du placement de l'ordre",
        type: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const cancelOrder = async (orderId: number) => {
    try {
      await api.delete(`/orders/${orderId}`)
      setOrders((prev) =>
        prev.map((o) => (o.id === orderId ? { ...o, status: 'cancelled' } : o)),
      )
      setMessage({ text: 'Ordre annulé', type: 'success' })
    } catch {
      setMessage({ text: "Erreur lors de l'annulation", type: 'error' })
    }
  }

  const pendingOrders = orders.filter((o) => o.status === 'pending')
  const historyOrders = orders.filter((o) => o.status !== 'pending')

  const statusIcon = (s: string) => {
    switch (s) {
      case 'pending':
        return <Clock size={14} className="text-yellow-400" />
      case 'filled':
        return <CheckCircle size={14} className="text-green-400" />
      case 'cancelled':
        return <XCircle size={14} className="text-gray-500" />
      default:
        return null
    }
  }

  const statusLabel = (s: string) => {
    switch (s) {
      case 'pending':
        return 'En attente'
      case 'filled':
        return 'Exécuté'
      case 'cancelled':
        return 'Annulé'
      default:
        return s
    }
  }

  const orderTypeLabel = (t: string) => {
    switch (t) {
      case 'market':
        return 'Market'
      case 'limit':
        return 'Limit'
      case 'stop_limit':
        return 'Stop-Limit'
      default:
        return t
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
    <div className="max-w-5xl">
      <div className="flex items-center gap-3 mb-6">
        <ShoppingCart className="text-blue-400" size={24} />
        <h2 className="text-2xl font-bold">Ordres manuels</h2>
        <button
          onClick={loadOrders}
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

      {/* Order form */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Nouvel ordre</h3>

        {/* Pair selector */}
        <div className="mb-4">
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

        {/* Direction: Buy / Sell */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-1">Direction</label>
          <div className="flex gap-2">
            <button
              onClick={() => setDirection('buy')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition ${
                direction === 'buy'
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              <TrendingUp size={16} />
              Acheter
            </button>
            <button
              onClick={() => setDirection('sell')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition ${
                direction === 'sell'
                  ? 'bg-red-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              <TrendingDown size={16} />
              Vendre
            </button>
          </div>
        </div>

        {/* Order type tabs */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-1">Type d'ordre</label>
          <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
            {(
              [
                { key: 'market', label: 'Market' },
                { key: 'limit', label: 'Limit' },
                { key: 'stop_limit', label: 'Stop-Limit' },
              ] as { key: OrderTypeTab; label: string }[]
            ).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setOrderType(tab.key)}
                className={`flex-1 py-2 rounded-md text-sm font-medium transition ${
                  orderType === tab.key
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Size */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-1">
            Taille (quantité)
          </label>
          <input
            type="number"
            step="any"
            min="0"
            value={size}
            onChange={(e) => setSize(e.target.value)}
            placeholder="0.001"
            className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
          />
        </div>

        {/* Price (for limit and stop_limit) */}
        {orderType !== 'market' && (
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">
              Prix limite (USD)
            </label>
            <input
              type="number"
              step="any"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="50000.00"
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>
        )}

        {/* Stop price (for stop_limit) */}
        {orderType === 'stop_limit' && (
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">
              Stop price (USD)
            </label>
            <input
              type="number"
              step="any"
              min="0"
              value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)}
              placeholder="49500.00"
              className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
            />
          </div>
        )}

        {/* Submit */}
        <button
          onClick={submitOrder}
          disabled={submitting || !size}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded-lg text-sm font-medium transition disabled:opacity-50 ${
            direction === 'buy'
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-red-600 hover:bg-red-700 text-white'
          }`}
        >
          {submitting ? (
            <Loader2 size={16} className="animate-spin" />
          ) : direction === 'buy' ? (
            <TrendingUp size={16} />
          ) : (
            <TrendingDown size={16} />
          )}
          {direction === 'buy' ? 'Acheter' : 'Vendre'} {pair}{' '}
          {orderType === 'market' ? '(Market)' : `(${orderTypeLabel(orderType)})`}
        </button>
      </div>

      {/* Pending orders */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Clock size={18} className="text-yellow-400" />
          Ordres en attente ({pendingOrders.length})
        </h3>
        {pendingOrders.length === 0 ? (
          <p className="text-gray-500 text-center py-6 text-sm">
            Aucun ordre en attente
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="text-left py-2 px-3">Paire</th>
                  <th className="text-left py-2 px-3">Direction</th>
                  <th className="text-left py-2 px-3">Type</th>
                  <th className="text-right py-2 px-3">Taille</th>
                  <th className="text-right py-2 px-3">Prix</th>
                  <th className="text-right py-2 px-3">Stop</th>
                  <th className="text-left py-2 px-3">Date</th>
                  <th className="text-center py-2 px-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {pendingOrders.map((o) => (
                  <tr
                    key={o.id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30"
                  >
                    <td className="py-2 px-3 font-medium">{o.pair}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                          o.direction === 'buy'
                            ? 'bg-green-500/10 text-green-400'
                            : 'bg-red-500/10 text-red-400'
                        }`}
                      >
                        {o.direction === 'buy' ? (
                          <TrendingUp size={10} />
                        ) : (
                          <TrendingDown size={10} />
                        )}
                        {o.direction === 'buy' ? 'Achat' : 'Vente'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-400">
                      {orderTypeLabel(o.order_type)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {o.size}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {o.price != null ? `$${o.price}` : '-'}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {o.stop_price != null ? `$${o.stop_price}` : '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-500 text-xs">
                      {o.created_at
                        ? new Date(o.created_at).toLocaleString('fr-FR')
                        : '-'}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <button
                        onClick={() => cancelOrder(o.id)}
                        className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-red-400 transition"
                        title="Annuler"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Order history */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h3 className="text-lg font-semibold mb-4">
          Historique des ordres ({historyOrders.length})
        </h3>
        {historyOrders.length === 0 ? (
          <p className="text-gray-500 text-center py-6 text-sm">
            Aucun historique
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="text-left py-2 px-3">Paire</th>
                  <th className="text-left py-2 px-3">Direction</th>
                  <th className="text-left py-2 px-3">Type</th>
                  <th className="text-right py-2 px-3">Taille</th>
                  <th className="text-right py-2 px-3">Prix exécuté</th>
                  <th className="text-right py-2 px-3">Frais</th>
                  <th className="text-left py-2 px-3">Statut</th>
                  <th className="text-left py-2 px-3">Date</th>
                </tr>
              </thead>
              <tbody>
                {historyOrders.map((o) => (
                  <tr
                    key={o.id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30"
                  >
                    <td className="py-2 px-3 font-medium">{o.pair}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                          o.direction === 'buy'
                            ? 'bg-green-500/10 text-green-400'
                            : 'bg-red-500/10 text-red-400'
                        }`}
                      >
                        {o.direction === 'buy' ? 'Achat' : 'Vente'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-400">
                      {orderTypeLabel(o.order_type)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {o.size}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">
                      {o.fill_price != null
                        ? `$${o.fill_price.toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                          })}`
                        : '-'}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-gray-500">
                      {o.fee > 0 ? `$${o.fee.toFixed(4)}` : '-'}
                    </td>
                    <td className="py-2 px-3">
                      <span className="inline-flex items-center gap-1 text-xs">
                        {statusIcon(o.status)}
                        {statusLabel(o.status)}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-500 text-xs">
                      {(o.filled_at || o.created_at)
                        ? new Date(
                            o.filled_at || o.created_at!,
                          ).toLocaleString('fr-FR')
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
