import { useEffect, useState, useRef } from 'react'
import { useApi } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { Terminal, Pause, Play, Trash2, Download } from 'lucide-react'

interface LogEntry {
  timestamp: string
  level: string
  event: string
  [key: string]: unknown
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-500',
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
}

export default function BotLogs({ token }: { token: string }) {
  const api = useApi(token)
  const { lastMessage, connected } = useWebSocket('/ws/logs')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load history on mount
  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/bot/logs?limit=200')
        if (Array.isArray(res.data)) {
          setLogs(res.data.reverse())
        }
      } catch {
        // API might not be available yet
      }
    }
    load()
  }, [token])

  // Append live logs from WebSocket
  useEffect(() => {
    if (!lastMessage || paused) return
    const msg = lastMessage as LogEntry
    if (msg.event && msg.event !== 'heartbeat' && msg.level) {
      setLogs((prev) => [...prev.slice(-499), msg])
    }
  }, [lastMessage, paused])

  // Auto-scroll
  useEffect(() => {
    if (!paused) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, paused])

  const filteredLogs = logs.filter((log) => {
    if (log.event === 'heartbeat') return false
    if (levelFilter !== 'ALL' && log.level !== levelFilter) return false
    if (filter) {
      const text = JSON.stringify(log).toLowerCase()
      if (!text.includes(filter.toLowerCase())) return false
    }
    return true
  })

  const handleExport = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] ${l.level} ${l.event} ${formatExtra(l)}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bot-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <Terminal size={24} className="text-green-400" />
          Bot Logs
        </h2>
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              connected ? 'bg-green-400' : 'bg-red-400'
            }`}
          />
          <span className={connected ? 'text-green-400' : 'text-red-400'}>
            {connected ? 'Live' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filtrer les logs..."
          className="flex-1 px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
        />
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
        >
          <option value="ALL">Tous</option>
          <option value="DEBUG">Debug</option>
          <option value="INFO">Info</option>
          <option value="WARNING">Warning</option>
          <option value="ERROR">Error</option>
        </select>
        <button
          onClick={() => setPaused(!paused)}
          className={`flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium transition ${
            paused
              ? 'bg-green-600 hover:bg-green-700'
              : 'bg-yellow-600 hover:bg-yellow-700'
          }`}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
          {paused ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={() => setLogs([])}
          className="flex items-center gap-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition"
        >
          <Trash2 size={14} />
        </button>
        <button
          onClick={handleExport}
          className="flex items-center gap-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition"
        >
          <Download size={14} />
        </button>
      </div>

      {/* Log viewer */}
      <div className="flex-1 bg-gray-950 rounded-xl border border-gray-800 overflow-auto font-mono text-xs p-4 min-h-0">
        {filteredLogs.length === 0 ? (
          <p className="text-gray-600 text-center py-8">
            Aucun log. Le bot publie ses logs en temps reel ici.
          </p>
        ) : (
          filteredLogs.map((log, i) => (
            <div key={i} className="flex gap-2 py-0.5 hover:bg-gray-900/50">
              <span className="text-gray-600 whitespace-nowrap">
                {formatTime(log.timestamp)}
              </span>
              <span
                className={`w-12 text-right ${
                  LEVEL_COLORS[log.level] || 'text-gray-400'
                }`}
              >
                {log.level}
              </span>
              <span className="text-purple-400 font-semibold">
                {log.event}
              </span>
              <span className="text-gray-400">{formatExtra(log)}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-2 text-xs text-gray-600">
        <span>{filteredLogs.length} logs affichés</span>
        <span>{logs.length} total en mémoire</span>
      </div>
    </div>
  )
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatExtra(log: LogEntry): string {
  const skip = new Set(['timestamp', 'level', 'event', 'type'])
  const parts: string[] = []
  for (const [k, v] of Object.entries(log)) {
    if (skip.has(k)) continue
    parts.push(`${k}=${v}`)
  }
  return parts.join(' ')
}
