import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Trade {
  id: number
  order_id: string
  pair: string
  direction: string
  size: number
  entry_price: number
  exit_price: number | null
  profit: number | null
  fee: number
  status: string
  strategy: string
  opened_at: string
  closed_at: string | null
}

export default function Trades({ token }: { token: string }) {
  const api = useApi(token)
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    api.get('/trades/?limit=100').then((r) => setTrades(r.data))
  }, [token])

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Trade History</h2>

      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 bg-gray-800/50">
              <th className="text-left px-4 py-3">Date</th>
              <th className="text-left px-4 py-3">Pair</th>
              <th className="text-left px-4 py-3">Direction</th>
              <th className="text-right px-4 py-3">Size</th>
              <th className="text-right px-4 py-3">Entry</th>
              <th className="text-right px-4 py-3">Exit</th>
              <th className="text-right px-4 py-3">P&L</th>
              <th className="text-left px-4 py-3">Strategy</th>
              <th className="text-left px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-t border-gray-800/50 hover:bg-gray-800/30">
                <td className="px-4 py-2 text-gray-400 text-xs">
                  {new Date(t.opened_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 font-mono">{t.pair}</td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      t.direction === 'buy'
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {t.direction.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-2 text-right font-mono">{t.size}</td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.entry_price.toFixed(2)}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.exit_price ? t.exit_price.toFixed(2) : '–'}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {t.profit != null ? (
                    <span
                      className={
                        t.profit >= 0 ? 'text-green-400' : 'text-red-400'
                      }
                    >
                      ${t.profit.toFixed(2)}
                    </span>
                  ) : (
                    '–'
                  )}
                </td>
                <td className="px-4 py-2 text-gray-400 text-xs">{t.strategy}</td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      t.status === 'OPEN'
                        ? 'bg-blue-500/20 text-blue-400'
                        : t.status === 'SHADOW'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-gray-700 text-gray-400'
                    }`}
                  >
                    {t.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
