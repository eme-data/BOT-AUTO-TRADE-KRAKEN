import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  Key,
  Shield,
  Bot,
  Bell,
  Brain,
  RefreshCw,
  CheckCircle,
  XCircle,
  Loader2,
  Eye,
  EyeOff,
  ShieldCheck,
  ShieldOff,
} from 'lucide-react'

interface FieldMeta {
  label: string
  type: string
  default: string | number | boolean
  options?: string[]
  value: string
  has_value: boolean
  sensitive?: boolean
}

type SchemaCategory = Record<string, FieldMeta>
type Schema = Record<string, SchemaCategory>

interface ConfigStatus {
  configured: boolean
  kraken_connected: boolean
  telegram_configured: boolean
  acc_type: string
}

const CATEGORY_META: Record<
  string,
  { title: string; description: string; icon: React.ReactNode }
> = {
  kraken: {
    title: 'Kraken API',
    description: 'Identifiants de connexion Kraken',
    icon: <Key size={20} />,
  },
  risk: {
    title: 'Gestion du risque',
    description: 'Limites de trading et taille des positions',
    icon: <Shield size={20} />,
  },
  autopilot: {
    title: 'Autopilot',
    description: 'Scan automatique et activation des paires',
    icon: <Bot size={20} />,
  },
  notifications: {
    title: 'Notifications Telegram',
    description: 'Alertes en temps reel via Telegram',
    icon: <Bell size={20} />,
  },
  ai: {
    title: 'Analyse IA (Claude)',
    description: 'Validation intelligente des trades par Claude AI — optionnel',
    icon: <Brain size={20} />,
  },
}

export default function Settings({ token }: { token: string }) {
  const api = useApi(token)
  const [schema, setSchema] = useState<Schema | null>(null)
  const [status, setStatus] = useState<ConfigStatus | null>(null)
  const [formData, setFormData] = useState<Record<string, Record<string, string>>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; balance_usd?: number; error?: string } | null>(null)
  const [visiblePasswords, setVisiblePasswords] = useState<Set<string>>(new Set())

  useEffect(() => {
    loadData()
  }, [token])

  const loadData = async () => {
    try {
      const [schemaRes, statusRes] = await Promise.all([
        api.get('/settings/schema'),
        api.get('/settings/status'),
      ])
      setSchema(schemaRes.data)
      setStatus(statusRes.data)

      // Initialize form data from schema
      const initial: Record<string, Record<string, string>> = {}
      for (const [cat, fields] of Object.entries(schemaRes.data as Schema)) {
        initial[cat] = {}
        for (const [key, meta] of Object.entries(fields)) {
          initial[cat][key] = meta.value || ''
        }
      }
      setFormData(initial)
    } catch {
      setMessage({ text: 'Erreur de chargement des parametres', type: 'error' })
    }
  }

  const handleFieldChange = (category: string, key: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [category]: { ...prev[category], [key]: value },
    }))
  }

  const handleSaveCategory = async (category: string) => {
    setSaving(category)
    setMessage(null)
    try {
      await api.put(`/settings/category/${category}`, {
        values: formData[category],
      })
      setMessage({ text: `${CATEGORY_META[category]?.title || category} mis a jour`, type: 'success' })
      // Reload status
      const statusRes = await api.get('/settings/status')
      setStatus(statusRes.data)
    } catch {
      setMessage({ text: 'Erreur lors de la sauvegarde', type: 'error' })
    } finally {
      setSaving(null)
    }
  }

  const handleTestConnection = async () => {
    const krakenData = formData['kraken']
    if (!krakenData) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post('/settings/test-connection', {
        api_key: krakenData['kraken_api_key'],
        api_secret: krakenData['kraken_api_secret'],
        acc_type: krakenData['kraken_acc_type'] || 'DEMO',
      })
      setTestResult(res.data)
    } catch {
      setTestResult({ success: false, error: 'Erreur de connexion' })
    } finally {
      setTesting(false)
    }
  }

  const handleReload = async () => {
    try {
      await api.post('/settings/reload')
      setMessage({ text: 'Rechargement envoye au bot', type: 'success' })
    } catch {
      setMessage({ text: 'Erreur lors du rechargement', type: 'error' })
    }
  }

  const togglePasswordVisibility = (key: string) => {
    setVisiblePasswords((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (!schema) {
    return <p className="text-gray-400">Chargement...</p>
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Configuration</h2>
        <button
          onClick={handleReload}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
        >
          <RefreshCw size={14} />
          Recharger le bot
        </button>
      </div>

      {/* Status banner */}
      {status && (
        <div
          className={`rounded-xl p-4 mb-6 border flex items-center gap-3 ${
            status.configured
              ? 'bg-green-500/10 border-green-500/30 text-green-400'
              : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
          }`}
        >
          {status.configured ? <CheckCircle size={20} /> : <XCircle size={20} />}
          <div>
            <p className="font-medium">
              {status.configured
                ? `Connecte a Kraken (${status.acc_type})`
                : 'Non configure — renseignez vos identifiants Kraken ci-dessous'}
            </p>
            {status.telegram_configured && (
              <p className="text-xs opacity-70 mt-0.5">Notifications Telegram actives</p>
            )}
          </div>
        </div>
      )}

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

      {/* Setting categories */}
      <div className="space-y-6">
        {Object.entries(schema).map(([category, fields]) => {
          const meta = CATEGORY_META[category] || {
            title: category,
            description: '',
            icon: null,
          }
          return (
            <div
              key={category}
              className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden"
            >
              {/* Category header */}
              <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-800/30">
                <div className="text-blue-400">{meta.icon}</div>
                <div>
                  <h3 className="font-semibold">{meta.title}</h3>
                  <p className="text-xs text-gray-500">{meta.description}</p>
                </div>
              </div>

              {/* Fields */}
              <div className="p-6 space-y-4">
                {Object.entries(fields).map(([key, fieldMeta]) => (
                  <SettingField
                    key={key}
                    fieldKey={key}
                    meta={fieldMeta}
                    value={formData[category]?.[key] ?? ''}
                    onChange={(val) => handleFieldChange(category, key, val)}
                    showPassword={visiblePasswords.has(key)}
                    onTogglePassword={() => togglePasswordVisibility(key)}
                  />
                ))}

                {/* Test connection button for Kraken category */}
                {category === 'kraken' && (
                  <div className="pt-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={testing}
                      className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition disabled:opacity-50"
                    >
                      {testing ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <CheckCircle size={14} />
                      )}
                      Tester la connexion
                    </button>
                    {testResult && (
                      <div
                        className={`mt-2 text-sm px-3 py-2 rounded-lg ${
                          testResult.success
                            ? 'bg-green-500/10 text-green-400'
                            : 'bg-red-500/10 text-red-400'
                        }`}
                      >
                        {testResult.success
                          ? `Connexion OK — Solde: $${testResult.balance_usd?.toFixed(2)}`
                          : `Echec: ${testResult.error}`}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Save button */}
              <div className="px-6 py-3 border-t border-gray-800 bg-gray-800/20 flex justify-end">
                <button
                  onClick={() => handleSaveCategory(category)}
                  disabled={saving === category}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
                >
                  {saving === category ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : null}
                  Enregistrer
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* 2FA Section */}
      <TwoFactorSection api={api} />

      {/* Bot control */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mt-6">
        <h3 className="text-lg font-semibold mb-4">Controle du bot</h3>
        <div className="flex gap-3">
          <button
            onClick={() => api.post('/bot/stop')}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition"
          >
            Arreter le bot
          </button>
          <button
            onClick={() => api.post('/bot/autopilot/scan')}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-sm font-medium transition"
          >
            Lancer un scan
          </button>
          <button
            onClick={() => api.post('/bot/daily-reset')}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition"
          >
            Reset journalier
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Field component ───────────────────────────────────

function SettingField({
  fieldKey: _fieldKey,
  meta,
  value,
  onChange,
  showPassword,
  onTogglePassword,
}: {
  fieldKey: string
  meta: FieldMeta
  value: string
  onChange: (val: string) => void
  showPassword: boolean
  onTogglePassword: () => void
}) {
  const baseInput =
    'w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none text-gray-100'

  if (meta.type === 'toggle') {
    const checked = value === 'true' || value === '1' || value === 'on'
    return (
      <div className="flex items-center justify-between">
        <label className="text-sm text-gray-300">{meta.label}</label>
        <button
          onClick={() => onChange(checked ? 'false' : 'true')}
          className={`relative w-11 h-6 rounded-full transition ${
            checked ? 'bg-blue-600' : 'bg-gray-700'
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
              checked ? 'translate-x-5' : ''
            }`}
          />
        </button>
      </div>
    )
  }

  if (meta.type === 'select' && meta.options) {
    return (
      <div>
        <label className="block text-sm text-gray-300 mb-1">{meta.label}</label>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        >
          {meta.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (meta.type === 'password') {
    return (
      <div>
        <label className="block text-sm text-gray-300 mb-1">{meta.label}</label>
        <div className="relative">
          <input
            type={showPassword ? 'text' : 'password'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={meta.has_value ? '(valeur enregistree)' : `Entrez ${meta.label}`}
            className={baseInput + ' pr-10'}
          />
          <button
            type="button"
            onClick={onTogglePassword}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        {meta.has_value && (
          <p className="text-xs text-green-500/70 mt-1">Valeur deja configuree</p>
        )}
      </div>
    )
  }

  // text / number
  return (
    <div>
      <label className="block text-sm text-gray-300 mb-1">{meta.label}</label>
      <input
        type={meta.type === 'number' ? 'number' : 'text'}
        step={meta.type === 'number' ? 'any' : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={String(meta.default ?? '')}
        className={baseInput}
      />
    </div>
  )
}


// ── 2FA Component ────────────────────────────────────

function TwoFactorSection({ api }: { api: ReturnType<typeof useApi> }) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [setupData, setSetupData] = useState<{ secret: string; qr_code: string } | null>(null)
  const [verifyCode, setVerifyCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [showDisable, setShowDisable] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [working, setWorking] = useState(false)

  useState(() => {
    api.get('/auth/2fa/status')
      .then(res => { setEnabled(res.data.enabled); setLoading(false) })
      .catch(() => setLoading(false))
  })

  const handleSetup = async () => {
    setWorking(true)
    setMessage(null)
    try {
      const res = await api.post('/auth/2fa/setup')
      setSetupData(res.data)
    } catch {
      setMessage({ text: 'Erreur lors de la configuration 2FA', type: 'error' })
    } finally { setWorking(false) }
  }

  const handleVerify = async () => {
    if (verifyCode.length !== 6) return
    setWorking(true)
    setMessage(null)
    try {
      await api.post('/auth/2fa/verify', { code: verifyCode })
      setEnabled(true)
      setSetupData(null)
      setVerifyCode('')
      setMessage({ text: '2FA active avec succes', type: 'success' })
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Code invalide', type: 'error' })
    } finally { setWorking(false) }
  }

  const handleDisable = async () => {
    if (disableCode.length !== 6) return
    setWorking(true)
    setMessage(null)
    try {
      await api.post('/auth/2fa/disable', { code: disableCode })
      setEnabled(false)
      setShowDisable(false)
      setDisableCode('')
      setMessage({ text: '2FA desactive', type: 'success' })
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Code invalide', type: 'error' })
    } finally { setWorking(false) }
  }

  if (loading) return null

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden mt-6">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-800/30">
        <div className="text-blue-400"><ShieldCheck size={20} /></div>
        <div>
          <h3 className="font-semibold">Authentification a deux facteurs (2FA)</h3>
          <p className="text-xs text-gray-500">Securisez votre compte avec Google Authenticator ou Authy</p>
        </div>
        <span className={`ml-auto px-2 py-0.5 rounded-full text-xs ${enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
          {enabled ? 'Active' : 'Desactive'}
        </span>
      </div>

      <div className="p-6">
        {message && (
          <div className={`rounded-lg px-4 py-2 mb-4 text-sm ${message.type === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
            {message.text}
          </div>
        )}

        {!enabled && !setupData && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Ajoutez une couche de securite supplementaire a votre compte.
            </p>
            <button
              onClick={handleSetup}
              disabled={working}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
            >
              {working ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
              Activer le 2FA
            </button>
          </div>
        )}

        {setupData && (
          <div className="space-y-4">
            <p className="text-sm text-gray-300">
              Scannez ce QR code avec votre application d'authentification :
            </p>
            <div className="flex justify-center">
              <img
                src={`data:image/png;base64,${setupData.qr_code}`}
                alt="QR Code 2FA"
                className="w-48 h-48 rounded-lg bg-white p-2"
              />
            </div>
            <div className="bg-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Cle secrete (saisie manuelle) :</p>
              <p className="font-mono text-sm text-gray-300 select-all break-all">{setupData.secret}</p>
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Entrez le code a 6 chiffres :</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  inputMode="numeric"
                  value={verifyCode}
                  onChange={e => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  maxLength={6}
                  placeholder="000000"
                  className="w-40 px-4 py-2 bg-gray-800 rounded-lg border border-gray-700 text-center text-lg tracking-widest focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={handleVerify}
                  disabled={working || verifyCode.length !== 6}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
                >
                  {working ? <Loader2 size={14} className="animate-spin" /> : 'Verifier'}
                </button>
                <button
                  onClick={() => { setSetupData(null); setVerifyCode('') }}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
                >
                  Annuler
                </button>
              </div>
            </div>
          </div>
        )}

        {enabled && !showDisable && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-green-400">
              La verification en deux etapes est active sur votre compte.
            </p>
            <button
              onClick={() => setShowDisable(true)}
              className="flex items-center gap-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-sm transition"
            >
              <ShieldOff size={14} />
              Desactiver
            </button>
          </div>
        )}

        {enabled && showDisable && (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">Entrez un code 2FA pour confirmer la desactivation :</p>
            <div className="flex gap-3">
              <input
                type="text"
                inputMode="numeric"
                value={disableCode}
                onChange={e => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                placeholder="000000"
                className="w-40 px-4 py-2 bg-gray-800 rounded-lg border border-gray-700 text-center text-lg tracking-widest focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={handleDisable}
                disabled={working || disableCode.length !== 6}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition disabled:opacity-50"
              >
                {working ? <Loader2 size={14} className="animate-spin" /> : 'Confirmer'}
              </button>
              <button
                onClick={() => { setShowDisable(false); setDisableCode('') }}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
              >
                Annuler
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
