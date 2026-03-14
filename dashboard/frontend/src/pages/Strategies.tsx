import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Zap,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle,
  XCircle,
  RotateCcw,
} from 'lucide-react'

interface StrategyData {
  name: string
  enabled: boolean
  config: Record<string, number | string | boolean>
  default_config: Record<string, number | string | boolean>
}

export default function Strategies({ token }: { token: string }) {
  const api = useApi(token)
  const [strategies, setStrategies] = useState<StrategyData[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [formData, setFormData] = useState<
    Record<string, { enabled: boolean; config: Record<string, string> }>
  >({})
  const [saving, setSaving] = useState<string | null>(null)
  const [message, setMessage] = useState<{
    text: string
    type: 'success' | 'error'
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStrategies()
  }, [token])

  const loadStrategies = async () => {
    setLoading(true)
    try {
      const res = await api.get('/strategies/')
      const data: StrategyData[] = res.data
      setStrategies(data)

      const initial: Record<
        string,
        { enabled: boolean; config: Record<string, string> }
      > = {}
      for (const s of data) {
        initial[s.name] = {
          enabled: s.enabled,
          config: Object.fromEntries(
            Object.entries(s.config).map(([k, v]) => [k, String(v)]),
          ),
        }
      }
      setFormData(initial)
    } catch {
      setMessage({ text: 'Failed to load strategies', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const handleToggle = (name: string) => {
    setFormData((prev) => ({
      ...prev,
      [name]: { ...prev[name], enabled: !prev[name].enabled },
    }))
  }

  const handleConfigChange = (name: string, key: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [name]: {
        ...prev[name],
        config: { ...prev[name].config, [key]: value },
      },
    }))
  }

  const handleResetConfig = (name: string) => {
    const strategy = strategies.find((s) => s.name === name)
    if (!strategy) return
    setFormData((prev) => ({
      ...prev,
      [name]: {
        ...prev[name],
        config: Object.fromEntries(
          Object.entries(strategy.default_config).map(([k, v]) => [
            k,
            String(v),
          ]),
        ),
      },
    }))
  }

  const handleSave = async (name: string) => {
    setSaving(name)
    setMessage(null)
    try {
      const form = formData[name]
      // Convert string values back to numbers where appropriate
      const config: Record<string, number | string | boolean> = {}
      for (const [k, v] of Object.entries(form.config)) {
        const num = Number(v)
        config[k] = isNaN(num) ? v : num
      }

      await api.put(`/strategies/${name}`, {
        enabled: form.enabled,
        config,
      })
      setMessage({
        text: `Strategy "${formatName(name)}" updated`,
        type: 'success',
      })
      // Reload to get fresh state
      const res = await api.get('/strategies/')
      setStrategies(res.data)
    } catch {
      setMessage({ text: 'Failed to save strategy', type: 'error' })
    } finally {
      setSaving(null)
    }
  }

  const formatName = (name: string) =>
    name
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ')

  if (loading) {
    return <p className="text-gray-400">Chargement...</p>
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Strategies</h2>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Zap size={16} className="text-blue-400" />
          {strategies.filter((s) => formData[s.name]?.enabled).length} /{' '}
          {strategies.length} active
        </div>
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

      {/* Strategy cards */}
      <div className="space-y-4">
        {strategies.map((strategy) => {
          const form = formData[strategy.name]
          if (!form) return null
          const isExpanded = expanded.has(strategy.name)

          return (
            <div
              key={strategy.name}
              className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden"
            >
              {/* Strategy header */}
              <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-800/30">
                <button
                  onClick={() => toggleExpand(strategy.name)}
                  className="text-gray-400 hover:text-gray-200 transition"
                >
                  {isExpanded ? (
                    <ChevronDown size={18} />
                  ) : (
                    <ChevronRight size={18} />
                  )}
                </button>

                <div className="text-blue-400">
                  <Zap size={20} />
                </div>

                <div className="flex-1">
                  <h3 className="font-semibold">
                    {formatName(strategy.name)}
                  </h3>
                  <p className="text-xs text-gray-500">
                    {Object.keys(strategy.default_config).length} configurable
                    parameter
                    {Object.keys(strategy.default_config).length !== 1
                      ? 's'
                      : ''}
                  </p>
                </div>

                {/* Toggle switch */}
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-medium ${
                      form.enabled ? 'text-green-400' : 'text-gray-500'
                    }`}
                  >
                    {form.enabled ? (
                      <span className="flex items-center gap-1">
                        <CheckCircle size={12} /> Enabled
                      </span>
                    ) : (
                      <span className="flex items-center gap-1">
                        <XCircle size={12} /> Disabled
                      </span>
                    )}
                  </span>
                  <button
                    onClick={() => handleToggle(strategy.name)}
                    className={`relative w-11 h-6 rounded-full transition ${
                      form.enabled ? 'bg-blue-600' : 'bg-gray-700'
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                        form.enabled ? 'translate-x-5' : ''
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Expandable config section */}
              {isExpanded && (
                <div className="p-6 space-y-4">
                  {Object.entries(form.config).map(([key, value]) => {
                    const defaultVal = strategy.default_config[key]
                    return (
                      <div key={key}>
                        <label className="block text-sm text-gray-300 mb-1">
                          {formatName(key)}
                          <span className="text-xs text-gray-600 ml-2">
                            (default: {String(defaultVal)})
                          </span>
                        </label>
                        <input
                          type="number"
                          step="any"
                          value={value}
                          onChange={(e) =>
                            handleConfigChange(
                              strategy.name,
                              key,
                              e.target.value,
                            )
                          }
                          placeholder={String(defaultVal)}
                          className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100"
                        />
                      </div>
                    )
                  })}

                  {/* Reset to defaults button */}
                  <button
                    onClick={() => handleResetConfig(strategy.name)}
                    className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition"
                  >
                    <RotateCcw size={12} />
                    Reset to defaults
                  </button>
                </div>
              )}

              {/* Save button */}
              <div className="px-6 py-3 border-t border-gray-800 bg-gray-800/20 flex justify-end">
                <button
                  onClick={() => handleSave(strategy.name)}
                  disabled={saving === strategy.name}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
                >
                  {saving === strategy.name ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : null}
                  Enregistrer
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {strategies.length === 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center">
          <Zap size={32} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">No strategies registered</p>
          <p className="text-xs text-gray-600 mt-1">
            Strategies are defined in the bot configuration
          </p>
        </div>
      )}
    </div>
  )
}
