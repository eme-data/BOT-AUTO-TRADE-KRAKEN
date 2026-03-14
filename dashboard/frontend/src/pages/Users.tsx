import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { UserPlus, Trash2, Edit3, Save, X, Loader2, Shield } from 'lucide-react'

interface UserData {
  id: number
  username: string
  role: string
  created_at: string | null
}

export default function Users({ token }: { token: string }) {
  const api = useApi(token)
  const [users, setUsers] = useState<UserData[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'viewer' })
  const [creating, setCreating] = useState(false)

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editData, setEditData] = useState({ role: '', password: '' })
  const [saving, setSaving] = useState(false)

  // Delete confirm
  const [deletingId, setDeletingId] = useState<number | null>(null)

  useEffect(() => {
    loadUsers()
  }, [token])

  const loadUsers = async () => {
    try {
      const res = await api.get('/users/')
      setUsers(res.data)
    } catch {
      setMessage({ text: 'Erreur de chargement des utilisateurs', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newUser.username || !newUser.password) {
      setMessage({ text: 'Nom d\'utilisateur et mot de passe requis', type: 'error' })
      return
    }
    setCreating(true)
    setMessage(null)
    try {
      await api.post('/users/', newUser)
      setMessage({ text: `Utilisateur "${newUser.username}" cree`, type: 'success' })
      setNewUser({ username: '', password: '', role: 'viewer' })
      setShowCreate(false)
      await loadUsers()
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erreur lors de la creation'
      setMessage({ text: detail, type: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const handleEdit = (user: UserData) => {
    setEditingId(user.id)
    setEditData({ role: user.role, password: '' })
  }

  const handleSaveEdit = async () => {
    if (editingId === null) return
    setSaving(true)
    setMessage(null)
    try {
      const payload: Record<string, string> = { role: editData.role }
      if (editData.password) payload.password = editData.password
      await api.put(`/users/${editingId}`, payload)
      setMessage({ text: 'Utilisateur mis a jour', type: 'success' })
      setEditingId(null)
      await loadUsers()
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erreur lors de la mise a jour'
      setMessage({ text: detail, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (userId: number) => {
    setMessage(null)
    try {
      await api.delete(`/users/${userId}`)
      setMessage({ text: 'Utilisateur supprime', type: 'success' })
      setDeletingId(null)
      await loadUsers()
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erreur lors de la suppression'
      setMessage({ text: detail, type: 'error' })
      setDeletingId(null)
    }
  }

  const roleColor = (role: string) => {
    switch (role) {
      case 'admin': return 'bg-red-500/20 text-red-400 border-red-500/30'
      case 'editor': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    }
  }

  if (loading) return <p className="text-gray-400">Chargement...</p>

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Gestion des utilisateurs</h2>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition"
        >
          <UserPlus size={16} />
          Nouvel utilisateur
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

      {/* Create form */}
      {showCreate && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Creer un utilisateur</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Nom d'utilisateur</label>
              <input
                type="text"
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                placeholder="john_doe"
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Mot de passe</label>
              <input
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                placeholder="••••••••"
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Role</label>
              <select
                value={newUser.role}
                onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="viewer">Viewer (lecture seule)</option>
                <option value="editor">Editor (lecture + modification)</option>
                <option value="admin">Admin (acces complet)</option>
              </select>
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              onClick={handleCreate}
              disabled={creating}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
            >
              {creating ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
              Creer
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
            >
              Annuler
            </button>
          </div>
        </div>
      )}

      {/* Users table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-800/30">
              <th className="text-left px-6 py-3 text-xs text-gray-500 font-medium uppercase">ID</th>
              <th className="text-left px-6 py-3 text-xs text-gray-500 font-medium uppercase">Utilisateur</th>
              <th className="text-left px-6 py-3 text-xs text-gray-500 font-medium uppercase">Role</th>
              <th className="text-left px-6 py-3 text-xs text-gray-500 font-medium uppercase">Cree le</th>
              <th className="text-right px-6 py-3 text-xs text-gray-500 font-medium uppercase">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                <td className="px-6 py-4 text-sm text-gray-500">#{user.id}</td>
                <td className="px-6 py-4 text-sm font-medium">{user.username}</td>
                <td className="px-6 py-4">
                  {editingId === user.id ? (
                    <select
                      value={editData.role}
                      onChange={(e) => setEditData({ ...editData, role: e.target.value })}
                      className="px-2 py-1 bg-gray-800 rounded border border-gray-700 text-xs focus:border-blue-500 focus:outline-none"
                    >
                      <option value="viewer">viewer</option>
                      <option value="editor">editor</option>
                      <option value="admin">admin</option>
                    </select>
                  ) : (
                    <span className={`px-2 py-1 rounded-full text-xs border ${roleColor(user.role)}`}>
                      {user.role}
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {user.created_at
                    ? new Date(user.created_at).toLocaleDateString('fr-FR', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                      })
                    : '-'}
                </td>
                <td className="px-6 py-4 text-right">
                  {editingId === user.id ? (
                    <div className="flex items-center justify-end gap-2">
                      <input
                        type="password"
                        value={editData.password}
                        onChange={(e) => setEditData({ ...editData, password: e.target.value })}
                        placeholder="Nouveau mdp (optionnel)"
                        className="px-2 py-1 bg-gray-800 rounded border border-gray-700 text-xs w-40 focus:border-blue-500 focus:outline-none"
                      />
                      <button
                        onClick={handleSaveEdit}
                        disabled={saving}
                        className="p-1.5 text-green-400 hover:bg-green-500/10 rounded transition"
                        title="Enregistrer"
                      >
                        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="p-1.5 text-gray-400 hover:bg-gray-700 rounded transition"
                        title="Annuler"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : deletingId === user.id ? (
                    <div className="flex items-center justify-end gap-2">
                      <span className="text-xs text-red-400">Confirmer ?</span>
                      <button
                        onClick={() => handleDelete(user.id)}
                        className="px-2 py-1 bg-red-600 hover:bg-red-700 rounded text-xs transition"
                      >
                        Oui
                      </button>
                      <button
                        onClick={() => setDeletingId(null)}
                        className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition"
                      >
                        Non
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleEdit(user)}
                        className="p-1.5 text-gray-400 hover:text-blue-400 hover:bg-blue-500/10 rounded transition"
                        title="Modifier"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => setDeletingId(user.id)}
                        className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded transition"
                        title="Supprimer"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500 text-sm">
                  Aucun utilisateur
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Roles explanation */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mt-6">
        <h3 className="text-sm font-semibold mb-3 text-gray-400">Roles disponibles</h3>
        <div className="space-y-2 text-xs text-gray-500">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full border ${roleColor('admin')}`}>admin</span>
            Acces complet : configuration, trading, gestion des utilisateurs
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full border ${roleColor('editor')}`}>editor</span>
            Modification des parametres de trading, consultation des données
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full border ${roleColor('viewer')}`}>viewer</span>
            Lecture seule : consultation du dashboard et des trades
          </div>
        </div>
      </div>
    </div>
  )
}
