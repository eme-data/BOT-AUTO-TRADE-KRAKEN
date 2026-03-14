import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { Shield, Loader2, Filter } from 'lucide-react'

interface AuditEntry {
  id: number
  user_id: number | null
  action: string
  resource: string | null
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  created_at: string | null
}

const ACTION_COLORS: Record<string, string> = {
  login: 'bg-blue-500/20 text-blue-400',
  settings_update: 'bg-yellow-500/20 text-yellow-400',
  user_created: 'bg-green-500/20 text-green-400',
  user_updated: 'bg-orange-500/20 text-orange-400',
  user_deleted: 'bg-red-500/20 text-red-400',
}

export default function AuditLog({ token }: { token: string }) {
  const api = useApi(token)
  const [logs, setLogs] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => { loadLogs() }, [filter])

  const loadLogs = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '200' })
      if (filter) params.set('action', filter)
      const res = await api.get(`/audit/logs?${params}`)
      setLogs(res.data)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  const actions = [...new Set(logs.map(l => l.action))].sort()

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Audit Log</h2>
        </div>
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-gray-500" />
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">Toutes les actions</option>
            {actions.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-400" size={32} />
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-800/30">
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">Date</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">User</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">Action</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">Resource</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">Details</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase">IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                  <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                    {log.created_at ? new Date(log.created_at).toLocaleString('fr-FR') : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-300">#{log.user_id}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${ACTION_COLORS[log.action] || 'bg-gray-500/20 text-gray-400'}`}>
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {log.resource && <span>{log.resource}{log.resource_id ? ` #${log.resource_id}` : ''}</span>}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 max-w-xs truncate">
                    {log.details ? JSON.stringify(log.details) : '-'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">{log.ip_address || '-'}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-gray-500 text-sm">
                    Aucune entree dans l'audit log
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
