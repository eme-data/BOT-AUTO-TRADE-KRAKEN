import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { BookOpen, Plus, Trash2, Edit3, Save, X, Loader2 } from 'lucide-react'

interface Note {
  id: number
  user_id: number
  trade_id: number | null
  content: string
  tags: string[] | null
  mood: string | null
  created_at: string | null
  updated_at: string | null
}

const MOODS = [
  { value: 'confident', label: 'Confiant', color: 'bg-green-500/20 text-green-400' },
  { value: 'neutral', label: 'Neutre', color: 'bg-gray-500/20 text-gray-400' },
  { value: 'uncertain', label: 'Incertain', color: 'bg-yellow-500/20 text-yellow-400' },
  { value: 'fearful', label: 'Craintif', color: 'bg-red-500/20 text-red-400' },
]

const TAG_PRESETS = ['bonne_entree', 'erreur', 'lecon', 'patience', 'overtrading', 'fomo', 'discipline']

export default function Journal({ token }: { token: string }) {
  const api = useApi(token)
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newNote, setNewNote] = useState({ content: '', mood: '', tags: [] as string[], trade_id: '' })
  const [creating, setCreating] = useState(false)

  // Edit
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editData, setEditData] = useState({ content: '', mood: '', tags: [] as string[] })
  const [saving, setSaving] = useState(false)

  useEffect(() => { loadNotes() }, [])

  const loadNotes = async () => {
    try {
      const res = await api.get('/trades/journal?limit=100')
      setNotes(res.data)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  const handleCreate = async () => {
    if (!newNote.content.trim()) {
      setMessage({ text: 'Le contenu est requis', type: 'error' })
      return
    }
    setCreating(true)
    setMessage(null)
    try {
      const tradeId = newNote.trade_id ? parseInt(newNote.trade_id) : 0
      const body: Record<string, unknown> = {
        content: newNote.content,
        tags: newNote.tags.length ? newNote.tags : null,
        mood: newNote.mood || null,
      }
      await api.post(`/trades/${tradeId || 0}/notes`, body)
      setMessage({ text: 'Note ajoutee', type: 'success' })
      setNewNote({ content: '', mood: '', tags: [], trade_id: '' })
      setShowCreate(false)
      await loadNotes()
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Erreur', type: 'error' })
    } finally { setCreating(false) }
  }

  const startEdit = (note: Note) => {
    setEditingId(note.id)
    setEditData({ content: note.content, mood: note.mood || '', tags: note.tags || [] })
  }

  const handleSaveEdit = async () => {
    if (editingId === null) return
    setSaving(true)
    try {
      await api.put(`/trades/notes/${editingId}`, {
        content: editData.content,
        mood: editData.mood || null,
        tags: editData.tags.length ? editData.tags : null,
      })
      setEditingId(null)
      setMessage({ text: 'Note mise a jour', type: 'success' })
      await loadNotes()
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Erreur', type: 'error' })
    } finally { setSaving(false) }
  }

  const handleDelete = async (noteId: number) => {
    try {
      await api.delete(`/trades/notes/${noteId}`)
      setMessage({ text: 'Note supprimee', type: 'success' })
      await loadNotes()
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Erreur', type: 'error' })
    }
  }

  const toggleTag = (tag: string, current: string[], setter: (t: string[]) => void) => {
    setter(current.includes(tag) ? current.filter(t => t !== tag) : [...current, tag])
  }

  const moodColor = (mood: string | null) => MOODS.find(m => m.value === mood)?.color || 'bg-gray-500/20 text-gray-400'

  if (loading) return (
    <div className="flex justify-center py-12">
      <Loader2 className="animate-spin text-blue-400" size={32} />
    </div>
  )

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <BookOpen size={24} className="text-blue-400" />
          <h2 className="text-2xl font-bold">Journal de Trading</h2>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition"
        >
          <Plus size={16} />
          Nouvelle note
        </button>
      </div>

      {message && (
        <div className={`rounded-lg px-4 py-2 mb-4 text-sm ${message.type === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
          {message.text}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Nouvelle note</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Trade ID (optionnel)</label>
              <input
                type="number"
                value={newNote.trade_id}
                onChange={e => setNewNote({ ...newNote, trade_id: e.target.value })}
                placeholder="Laisser vide pour note generale"
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Contenu</label>
              <textarea
                value={newNote.content}
                onChange={e => setNewNote({ ...newNote, content: e.target.value })}
                rows={4}
                placeholder="Reflexions sur le trade, lecons apprises..."
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none resize-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-2">Humeur</label>
              <div className="flex gap-2">
                {MOODS.map(m => (
                  <button
                    key={m.value}
                    onClick={() => setNewNote({ ...newNote, mood: newNote.mood === m.value ? '' : m.value })}
                    className={`px-3 py-1.5 rounded-lg text-xs border transition ${newNote.mood === m.value ? m.color + ' border-current' : 'border-gray-700 text-gray-500 hover:border-gray-600'}`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-2">Tags</label>
              <div className="flex flex-wrap gap-2">
                {TAG_PRESETS.map(tag => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag, newNote.tags, t => setNewNote({ ...newNote, tags: t }))}
                    className={`px-2 py-1 rounded text-xs border transition ${newNote.tags.includes(tag) ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : 'border-gray-700 text-gray-500 hover:border-gray-600'}`}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
              >
                {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Creer
              </button>
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition">
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Notes list */}
      <div className="space-y-4">
        {notes.map(note => (
          <div key={note.id} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
            {editingId === note.id ? (
              <div className="space-y-3">
                <textarea
                  value={editData.content}
                  onChange={e => setEditData({ ...editData, content: e.target.value })}
                  rows={3}
                  className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none resize-none"
                />
                <div className="flex gap-2">
                  {MOODS.map(m => (
                    <button
                      key={m.value}
                      onClick={() => setEditData({ ...editData, mood: editData.mood === m.value ? '' : m.value })}
                      className={`px-2 py-1 rounded text-xs border transition ${editData.mood === m.value ? m.color + ' border-current' : 'border-gray-700 text-gray-500'}`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  {TAG_PRESETS.map(tag => (
                    <button
                      key={tag}
                      onClick={() => toggleTag(tag, editData.tags, t => setEditData({ ...editData, tags: t }))}
                      className={`px-2 py-1 rounded text-xs border transition ${editData.tags.includes(tag) ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : 'border-gray-700 text-gray-500'}`}
                    >
                      #{tag}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSaveEdit} disabled={saving} className="p-1.5 text-green-400 hover:bg-green-500/10 rounded transition">
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  </button>
                  <button onClick={() => setEditingId(null)} className="p-1.5 text-gray-400 hover:bg-gray-700 rounded transition">
                    <X size={14} />
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <p className="text-sm text-gray-200 whitespace-pre-wrap">{note.content}</p>
                    <div className="flex items-center gap-3 mt-3">
                      <span className="text-xs text-gray-500">
                        {note.created_at ? new Date(note.created_at).toLocaleString('fr-FR') : ''}
                      </span>
                      {note.trade_id && note.trade_id > 0 && (
                        <span className="text-xs bg-gray-800 px-2 py-0.5 rounded text-gray-400">
                          Trade #{note.trade_id}
                        </span>
                      )}
                      {note.mood && (
                        <span className={`text-xs px-2 py-0.5 rounded ${moodColor(note.mood)}`}>
                          {MOODS.find(m => m.value === note.mood)?.label || note.mood}
                        </span>
                      )}
                    </div>
                    {note.tags && note.tags.length > 0 && (
                      <div className="flex gap-1.5 mt-2">
                        {note.tags.map(tag => (
                          <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(note)} className="p-1.5 text-gray-400 hover:text-blue-400 hover:bg-blue-500/10 rounded transition">
                      <Edit3 size={14} />
                    </button>
                    <button onClick={() => handleDelete(note.id)} className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded transition">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        ))}
        {notes.length === 0 && (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
            <BookOpen size={48} className="text-gray-700 mx-auto mb-4" />
            <p className="text-gray-500">Aucune note dans votre journal</p>
            <p className="text-gray-600 text-sm mt-1">Commencez a documenter vos reflexions de trading</p>
          </div>
        )}
      </div>
    </div>
  )
}
