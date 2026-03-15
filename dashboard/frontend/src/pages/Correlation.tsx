import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface CorrelationData {
  pairs: string[]
  matrix: number[][]
  simulated: boolean
  note?: string
}

const DAYS_OPTIONS = [
  { label: '7 days', value: 7 },
  { label: '14 days', value: 14 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
]

function correlationColor(value: number): string {
  // Dark red (-1) -> white (0) -> dark green (+1)
  if (value >= 0) {
    const intensity = Math.round(value * 180)
    return `rgb(${220 - intensity}, ${220 + Math.round(value * 35)}, ${220 - intensity})`
  } else {
    const intensity = Math.round(Math.abs(value) * 180)
    return `rgb(${220 + Math.round(Math.abs(value) * 35)}, ${220 - intensity}, ${220 - intensity})`
  }
}

function textColor(value: number): string {
  return Math.abs(value) > 0.6 ? '#fff' : '#1a1a2e'
}

export default function Correlation({ token }: { token: string }) {
  const api = useApi(token)
  const [data, setData] = useState<CorrelationData | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api
      .get(`/analytics/correlation?days=${days}`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [token, days])

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Correlation Analysis</h2>

      {/* Period selector */}
      <div className="flex items-center gap-3 mb-6">
        <span className="text-sm text-gray-400">Period:</span>
        <div className="flex gap-1">
          {DAYS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setDays(opt.value)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                days === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="text-gray-400 text-center py-12">Loading correlation data...</div>
      )}

      {!loading && !data && (
        <div className="text-gray-400 text-center py-12">
          Unable to load correlation data.
        </div>
      )}

      {!loading && data && (
        <>
          {/* Simulated data banner */}
          {data.simulated && data.note && (
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl px-4 py-3 mb-6 text-sm text-yellow-300">
              {data.note}
            </div>
          )}

          {/* Heatmap */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6 overflow-x-auto">
            <h3 className="text-lg font-semibold mb-4">Pair Correlation Heatmap</h3>
            <div className="inline-block">
              <table className="border-collapse">
                <thead>
                  <tr>
                    <th className="w-20"></th>
                    {data.pairs.map((pair) => (
                      <th
                        key={pair}
                        className="px-2 py-2 text-xs font-mono text-gray-400 text-center"
                        style={{ minWidth: '72px' }}
                      >
                        {pair}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.pairs.map((rowPair, i) => (
                    <tr key={rowPair}>
                      <td className="px-2 py-2 text-xs font-mono text-gray-400 text-right pr-3">
                        {rowPair}
                      </td>
                      {data.matrix[i].map((value, j) => (
                        <td
                          key={`${i}-${j}`}
                          className="px-2 py-2 text-center text-xs font-mono font-semibold border border-gray-800"
                          style={{
                            backgroundColor: correlationColor(value),
                            color: textColor(value),
                            minWidth: '72px',
                            minHeight: '40px',
                          }}
                        >
                          {value.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 mt-6">
              <span className="text-xs text-gray-500">Strong negative</span>
              <div className="flex h-4 rounded overflow-hidden" style={{ width: '200px' }}>
                {Array.from({ length: 20 }, (_, i) => {
                  const val = -1 + (i / 19) * 2
                  return (
                    <div
                      key={i}
                      className="flex-1"
                      style={{ backgroundColor: correlationColor(val) }}
                    />
                  )
                })}
              </div>
              <span className="text-xs text-gray-500">Strong positive</span>
            </div>
          </div>

          {/* Interpretation */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h3 className="text-lg font-semibold mb-3">Understanding Correlation</h3>
            <div className="space-y-3 text-sm text-gray-400 leading-relaxed">
              <p>
                <span className="font-medium text-gray-200">Correlation</span> measures how two
                assets move together over time, on a scale from -1 to +1.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <div className="font-semibold text-green-400 mb-1">+0.7 to +1.0</div>
                  <div>
                    <strong>Strong positive correlation.</strong> These pairs tend to move in
                    the same direction. Holding both increases concentration risk.
                  </div>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <div className="font-semibold text-gray-300 mb-1">-0.3 to +0.3</div>
                  <div>
                    <strong>Low correlation.</strong> These pairs move mostly independently.
                    Good for portfolio diversification.
                  </div>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <div className="font-semibold text-red-400 mb-1">-1.0 to -0.7</div>
                  <div>
                    <strong>Strong negative correlation.</strong> These pairs tend to move in
                    opposite directions. Useful for hedging strategies.
                  </div>
                </div>
              </div>
              <p className="mt-3">
                For optimal diversification, aim to trade pairs with low or negative correlation.
                Highly correlated pairs amplify both gains and losses, while uncorrelated pairs
                help smooth overall portfolio performance.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
