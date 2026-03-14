import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { Key, CheckCircle, XCircle, Loader2, ArrowRight } from 'lucide-react'

interface SetupProps {
  token: string
  onComplete: () => void
}

export default function Setup({ token, onComplete }: SetupProps) {
  const api = useApi(token)
  const [step, setStep] = useState(1)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [accType, setAccType] = useState('DEMO')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    balance_usd?: number
    error?: string
  } | null>(null)
  const [saving, setSaving] = useState(false)

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post('/settings/test-connection', {
        api_key: apiKey,
        api_secret: apiSecret,
        acc_type: accType,
      })
      setTestResult(res.data)
      if (res.data.success) setStep(2)
    } catch {
      setTestResult({ success: false, error: 'Erreur de connexion' })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put('/settings/category/kraken', {
        values: {
          kraken_api_key: apiKey,
          kraken_api_secret: apiSecret,
          kraken_acc_type: accType,
        },
      })
      onComplete()
    } catch {
      // error
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-800 shadow-xl w-full max-w-lg p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex p-3 rounded-xl bg-blue-500/10 text-blue-400 mb-4">
            <Key size={28} />
          </div>
          <h1 className="text-2xl font-bold">Configuration initiale</h1>
          <p className="text-gray-500 text-sm mt-2">
            Connectez votre compte Kraken pour commencer le trading automatique
          </p>
        </div>

        {/* Steps indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step >= 1 ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-500'
            }`}
          >
            1
          </div>
          <div className="w-12 h-0.5 bg-gray-800" />
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-500'
            }`}
          >
            2
          </div>
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                Type de compte
              </label>
              <select
                value={accType}
                onChange={(e) => setAccType(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="DEMO">DEMO (Paper Trading)</option>
                <option value="LIVE">LIVE (Trading reel)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-1">
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Votre cle API Kraken"
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-1">
                API Secret
              </label>
              <input
                type="password"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                placeholder="Votre secret API Kraken"
                className="w-full px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>

            {accType === 'LIVE' && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
                Attention : le mode LIVE effectuera de vrais trades avec votre argent.
                Commencez par le mode DEMO pour tester.
              </div>
            )}

            {testResult && (
              <div
                className={`rounded-lg p-3 text-sm flex items-center gap-2 ${
                  testResult.success
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-red-500/10 text-red-400'
                }`}
              >
                {testResult.success ? (
                  <>
                    <CheckCircle size={16} />
                    Connexion OK — Solde: ${testResult.balance_usd?.toFixed(2)}
                  </>
                ) : (
                  <>
                    <XCircle size={16} />
                    {testResult.error}
                  </>
                )}
              </div>
            )}

            <button
              onClick={handleTest}
              disabled={!apiKey || !apiSecret || testing}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg font-medium transition flex items-center justify-center gap-2"
            >
              {testing ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              Tester la connexion
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="text-center space-y-6">
            <div className="inline-flex p-4 rounded-full bg-green-500/10 text-green-400">
              <CheckCircle size={40} />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Connexion reussie !</h3>
              <p className="text-gray-500 text-sm mt-1">
                Vos identifiants seront chiffres et stockes en base de donnees.
                Vous pourrez les modifier dans les parametres.
              </p>
            </div>
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full py-2.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded-lg font-medium transition flex items-center justify-center gap-2"
            >
              {saving ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <CheckCircle size={16} />
              )}
              Enregistrer et demarrer
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
