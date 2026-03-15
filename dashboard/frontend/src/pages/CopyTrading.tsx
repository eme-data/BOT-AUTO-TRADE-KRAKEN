import { useEffect, useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import { TrendingUp, Users, Copy, Loader2, RefreshCw, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'

/* -- Types -------------------------------------------------- */

interface LeaderStats {
  user_id: number
  username: string
  total_trades: number
  total_pnl: number
  win_rate: number
}

interface CopyLink {
  id: number
  follower_id: number
  leader_id: number
  active: boolean
  multiplier: number
  max_per_trade: number | null
  created_at: string | null
}

/* -- Component ----------------------------------------------- */

export default function CopyTrading({ token }: { token: string }) {
  const api = useApi(token)

  const [loading, setLoading] = useState(true)
  const [leaders, setLeaders] = useState<LeaderStats[]>([])
  const [links, setLinks] = useState<CopyLink[]>([])

  // Follow form state
  const [followingId, setFollowingId] = useState<number | null>(null)
  const [multiplier, setMultiplier] = useState(1.0)
  const [maxPerTrade, setMaxPerTrade] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [leadersRes, linksRes] = await Promise.all([
        api.get('/copy-trading/leaders'),
        api.get('/copy-trading/links'),
      ])
      setLeaders(leadersRes.data)
      setLinks(linksRes.data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { loadData() }, [])

  const handleFollow = async (leaderId: number) => {
    setError('')
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = { leader_id: leaderId, multiplier }
      if (maxPerTrade) body.max_per_trade = parseFloat(maxPerTrade)
      await api.post('/copy-trading/follow', body)
      setFollowingId(null)
      setMultiplier(1.0)
      setMaxPerTrade('')
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erreur lors du suivi')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (linkId: number) => {
    try {
      await api.put(`/copy-trading/${linkId}/toggle`)
      await loadData()
    } catch {
      /* ignore */
    }
  }

  const handleDelete = async (linkId: number) => {
    try {
      await api.delete(`/copy-trading/${linkId}`)
      await loadData()
    } catch {
      /* ignore */
    }
  }

  // Resolve leader username from id
  const leaderName = (leaderId: number) => {
    const leader = leaders.find(l => l.user_id === leaderId)
    return leader?.username || `User #${leaderId}`
  }

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
          <Copy size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Copy Trading</h2>
        </div>
        <button
          onClick={() => loadData()}
          className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 text-sm transition"
        >
          <RefreshCw size={14} />
          Rafraichir
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/20 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Leaders table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={18} className="text-blue-400" />
          <h3 className="font-semibold text-lg">Leaders</h3>
        </div>

        {leaders.length === 0 ? (
          <div className="text-center py-8">
            <Users size={48} className="text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500">Aucun leader disponible</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-800">
                  <th className="pb-3 pr-4">Trader</th>
                  <th className="pb-3 pr-4 text-right">Trades</th>
                  <th className="pb-3 pr-4 text-right">P&L total</th>
                  <th className="pb-3 pr-4 text-right">Win rate</th>
                  <th className="pb-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {leaders.map(leader => {
                  const isExpanded = followingId === leader.user_id
                  const alreadyFollowing = links.some(
                    l => l.leader_id === leader.user_id && l.active
                  )
                  return (
                    <tr key={leader.user_id} className="border-b border-gray-800/50">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-xs font-bold">
                            {leader.username.charAt(0).toUpperCase()}
                          </div>
                          <span className="font-medium">{leader.username}</span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-right text-gray-300">{leader.total_trades}</td>
                      <td className={`py-3 pr-4 text-right font-medium ${leader.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {leader.total_pnl >= 0 ? '+' : ''}{leader.total_pnl.toFixed(2)} $
                      </td>
                      <td className="py-3 pr-4 text-right text-gray-300">{leader.win_rate}%</td>
                      <td className="py-3 text-right">
                        {alreadyFollowing ? (
                          <span className="text-xs text-green-400 bg-green-500/20 px-2 py-1 rounded-full">
                            Suivi
                          </span>
                        ) : isExpanded ? (
                          <div className="flex flex-col items-end gap-2">
                            <div className="flex items-center gap-2">
                              <label className="text-xs text-gray-400">Mult:</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0.1"
                                max="10"
                                value={multiplier}
                                onChange={e => setMultiplier(parseFloat(e.target.value) || 1)}
                                className="w-16 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-center focus:border-blue-500 focus:outline-none"
                              />
                              <label className="text-xs text-gray-400">Max $:</label>
                              <input
                                type="number"
                                step="1"
                                min="0"
                                value={maxPerTrade}
                                onChange={e => setMaxPerTrade(e.target.value)}
                                placeholder="illimite"
                                className="w-20 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-center focus:border-blue-500 focus:outline-none"
                              />
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => setFollowingId(null)}
                                className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded border border-gray-700 transition"
                              >
                                Annuler
                              </button>
                              <button
                                onClick={() => handleFollow(leader.user_id)}
                                disabled={submitting}
                                className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 rounded font-medium transition disabled:opacity-50"
                              >
                                {submitting ? 'Envoi...' : 'Confirmer'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              setFollowingId(leader.user_id)
                              setMultiplier(1.0)
                              setMaxPerTrade('')
                              setError('')
                            }}
                            className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 rounded font-medium transition"
                          >
                            Copier
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* My subscriptions */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Users size={18} className="text-blue-400" />
          <h3 className="font-semibold text-lg">Mes abonnements</h3>
        </div>

        {links.length === 0 ? (
          <div className="text-center py-8">
            <Copy size={48} className="text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500">Aucun abonnement actif</p>
            <p className="text-gray-600 text-xs mt-1">Cliquez sur "Copier" pour suivre un leader</p>
          </div>
        ) : (
          <div className="space-y-3">
            {links.map(link => (
              <div
                key={link.id}
                className={`flex items-center justify-between p-4 rounded-lg border ${
                  link.active
                    ? 'bg-gray-800 border-gray-700'
                    : 'bg-gray-800/50 border-gray-800 opacity-60'
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold">
                    {leaderName(link.leader_id).charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-medium">{leaderName(link.leader_id)}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
                      <span>Multiplicateur: x{link.multiplier}</span>
                      <span>Max: {link.max_per_trade ? `${link.max_per_trade} $` : 'illimite'}</span>
                      <span className={`px-1.5 py-0.5 rounded ${link.active ? 'bg-green-500/20 text-green-400' : 'bg-gray-600/30 text-gray-500'}`}>
                        {link.active ? 'Actif' : 'Inactif'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(link.id)}
                    className="p-2 hover:bg-gray-700 rounded-lg transition"
                    title={link.active ? 'Desactiver' : 'Activer'}
                  >
                    {link.active ? (
                      <ToggleRight size={20} className="text-green-400" />
                    ) : (
                      <ToggleLeft size={20} className="text-gray-500" />
                    )}
                  </button>
                  <button
                    onClick={() => handleDelete(link.id)}
                    className="p-2 hover:bg-red-500/20 rounded-lg transition text-gray-500 hover:text-red-400"
                    title="Supprimer"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
