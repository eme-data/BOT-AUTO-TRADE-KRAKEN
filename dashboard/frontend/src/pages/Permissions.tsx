import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { Shield, Check, X as XIcon, Loader2, ExternalLink } from 'lucide-react'

interface RolePermissions {
  can_trade: boolean
  can_view_trades: boolean
  can_manage_settings: boolean
  can_manage_users: boolean
  can_backtest: boolean
  can_use_ai: boolean
  can_export: boolean
}

type RolesMap = Record<string, RolePermissions>

const PERMISSION_LABELS: Record<string, string> = {
  can_trade: 'Executer des trades',
  can_view_trades: 'Voir les trades',
  can_manage_settings: 'Gerer les parametres',
  can_manage_users: 'Gerer les utilisateurs',
  can_backtest: 'Lancer des backtests',
  can_use_ai: 'Utiliser l\'analyse IA',
  can_export: 'Exporter les donnees',
}

const PERMISSION_DESCRIPTIONS: Record<string, string> = {
  can_trade: 'Permet d\'ouvrir et fermer des positions sur le marche.',
  can_view_trades: 'Permet de consulter l\'historique et les trades en cours.',
  can_manage_settings: 'Permet de modifier la configuration du bot et du dashboard.',
  can_manage_users: 'Permet de creer, modifier et supprimer des utilisateurs.',
  can_backtest: 'Permet de lancer des simulations de strategies sur des donnees historiques.',
  can_use_ai: 'Permet d\'utiliser les outils d\'analyse propulses par l\'IA.',
  can_export: 'Permet d\'exporter les rapports et donnees au format CSV/PDF.',
}

const ROLE_COLORS: Record<string, string> = {
  admin: 'text-red-400',
  trader: 'text-blue-400',
  analyst: 'text-yellow-400',
  viewer: 'text-gray-400',
}

export default function Permissions({ token }: { token: string }) {
  const api = useApi(token)
  const [roles, setRoles] = useState<RolesMap | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRoles()
  }, [token])

  const loadRoles = async () => {
    try {
      const res = await api.get('/permissions/roles')
      setRoles(res.data)
    } catch {
      setError('Erreur lors du chargement des permissions')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400">
        <Loader2 size={18} className="animate-spin" />
        Chargement...
      </div>
    )
  }

  if (error || !roles) {
    return <p className="text-red-400">{error || 'Erreur inconnue'}</p>
  }

  const roleNames = Object.keys(roles)
  const permissionKeys = Object.keys(roles[roleNames[0]] || {})

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Shield size={24} className="text-blue-400" />
        <h2 className="text-2xl font-bold">Permissions par role</h2>
      </div>

      {/* Permissions matrix */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-800/30">
              <th className="text-left px-6 py-3 text-xs text-gray-500 font-medium uppercase">
                Permission
              </th>
              {roleNames.map((role) => (
                <th
                  key={role}
                  className={`text-center px-4 py-3 text-xs font-medium uppercase ${ROLE_COLORS[role] || 'text-gray-400'}`}
                >
                  {role}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {permissionKeys.map((perm) => (
              <tr key={perm} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                <td className="px-6 py-4">
                  <div className="text-sm font-medium text-gray-200">
                    {PERMISSION_LABELS[perm] || perm}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {PERMISSION_DESCRIPTIONS[perm] || ''}
                  </div>
                </td>
                {roleNames.map((role) => (
                  <td key={role} className="text-center px-4 py-4">
                    {roles[role][perm as keyof RolePermissions] ? (
                      <Check size={18} className="inline text-green-400" />
                    ) : (
                      <XIcon size={18} className="inline text-gray-600" />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Role descriptions */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mt-6">
        <h3 className="text-sm font-semibold mb-4 text-gray-400">Description des roles</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-950 rounded-lg p-4 border border-gray-800">
            <span className="text-red-400 font-semibold text-sm">Admin</span>
            <p className="text-xs text-gray-500 mt-1">
              Acces complet a toutes les fonctionnalites : trading, configuration, gestion des utilisateurs et export.
            </p>
          </div>
          <div className="bg-gray-950 rounded-lg p-4 border border-gray-800">
            <span className="text-blue-400 font-semibold text-sm">Trader</span>
            <p className="text-xs text-gray-500 mt-1">
              Peut executer des trades, lancer des backtests et utiliser l'IA. Ne peut pas gerer les parametres ou les utilisateurs.
            </p>
          </div>
          <div className="bg-gray-950 rounded-lg p-4 border border-gray-800">
            <span className="text-yellow-400 font-semibold text-sm">Analyst</span>
            <p className="text-xs text-gray-500 mt-1">
              Acces en lecture aux trades, backtests et analyse IA. Ne peut pas executer de trades ni modifier les parametres.
            </p>
          </div>
          <div className="bg-gray-950 rounded-lg p-4 border border-gray-800">
            <span className="text-gray-400 font-semibold text-sm">Viewer</span>
            <p className="text-xs text-gray-500 mt-1">
              Lecture seule : peut uniquement consulter les trades en cours et l'historique.
            </p>
          </div>
        </div>
      </div>

      {/* Link to users page */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 mt-6 flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-300">Pour modifier le role d'un utilisateur, rendez-vous sur la page de gestion des utilisateurs.</p>
        </div>
        <a
          href="#users"
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition whitespace-nowrap"
        >
          <ExternalLink size={14} />
          Gestion des utilisateurs
        </a>
      </div>
    </div>
  )
}
