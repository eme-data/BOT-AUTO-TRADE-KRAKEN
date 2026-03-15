import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  CalendarDays,
  Landmark,
  TrendingUp,
  Briefcase,
  BarChart3,
  Bitcoin,
  Filter,
  Clock,
  AlertTriangle,
} from 'lucide-react'

interface CalendarEvent {
  date: string
  title: string
  description: string
  impact: 'high' | 'medium' | 'low'
  category: 'fed' | 'inflation' | 'employment' | 'gdp' | 'crypto'
}

const IMPACT_STYLES: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  high: { label: 'Fort', bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400' },
  medium: { label: 'Moyen', bg: 'bg-yellow-500/10', text: 'text-yellow-400', dot: 'bg-yellow-400' },
  low: { label: 'Faible', bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-400' },
}

const CATEGORY_CONFIG: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  fed: { label: 'Fed / BCE', icon: <Landmark size={14} />, color: 'text-purple-400' },
  inflation: { label: 'Inflation', icon: <TrendingUp size={14} />, color: 'text-orange-400' },
  employment: { label: 'Emploi', icon: <Briefcase size={14} />, color: 'text-blue-400' },
  gdp: { label: 'PIB', icon: <BarChart3 size={14} />, color: 'text-green-400' },
  crypto: { label: 'Crypto', icon: <Bitcoin size={14} />, color: 'text-yellow-400' },
}

export default function Calendar({ token }: { token: string }) {
  const api = useApi(token)
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [todayEvents, setTodayEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(60)
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set())

  useEffect(() => {
    loadEvents()
  }, [token, days])

  const loadEvents = async () => {
    setLoading(true)
    try {
      const [eventsRes, todayRes] = await Promise.all([
        api.get(`/calendar/events?days=${days}`),
        api.get('/calendar/today'),
      ])
      setEvents(eventsRes.data)
      setTodayEvents(todayRes.data)
    } catch {
      // Calendar might not be available
    } finally {
      setLoading(false)
    }
  }

  const toggleFilter = (category: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }

  const filteredEvents = activeFilters.size > 0
    ? events.filter((e) => activeFilters.has(e.category))
    : events

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('fr-FR', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }

  const isWithin48h = (iso: string) => {
    const eventDate = new Date(iso)
    const now = new Date()
    const diff = eventDate.getTime() - now.getTime()
    return diff >= 0 && diff <= 48 * 60 * 60 * 1000
  }

  const isToday = (iso: string) => {
    const eventDate = new Date(iso)
    const now = new Date()
    return eventDate.toDateString() === now.toDateString()
  }

  const daysUntil = (iso: string) => {
    const eventDate = new Date(iso)
    const now = new Date()
    const diff = Math.ceil((eventDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
    if (diff === 0) return "Aujourd'hui"
    if (diff === 1) return 'Demain'
    if (diff < 0) return 'Passe'
    return `Dans ${diff} jours`
  }

  // Group events by month
  const groupedEvents: Record<string, CalendarEvent[]> = {}
  for (const event of filteredEvents) {
    const d = new Date(event.date)
    const key = d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
    if (!groupedEvents[key]) groupedEvents[key] = []
    groupedEvents[key].push(event)
  }

  if (loading) return <p className="text-gray-400">Chargement...</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <CalendarDays size={24} className="text-indigo-400" />
          Calendrier Economique
        </h2>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700 text-sm focus:border-blue-500 focus:outline-none"
        >
          <option value={30}>30 jours</option>
          <option value={60}>60 jours</option>
          <option value={90}>90 jours</option>
          <option value={180}>6 mois</option>
          <option value={365}>1 an</option>
        </select>
      </div>

      {/* Alert banner for imminent events */}
      {todayEvents.length > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-yellow-400" />
            <span className="text-yellow-400 font-semibold text-sm">
              {todayEvents.length} evenement{todayEvents.length > 1 ? 's' : ''} dans les prochaines 48h
            </span>
          </div>
          <div className="space-y-2">
            {todayEvents.map((event, i) => {
              const impact = IMPACT_STYLES[event.impact]
              const cat = CATEGORY_CONFIG[event.category]
              return (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <Clock size={14} className="text-yellow-500/60 flex-shrink-0" />
                  <span className={cat?.color || 'text-gray-400'}>{cat?.icon}</span>
                  <span className="text-gray-300">{event.title}</span>
                  <span className="text-gray-600 text-xs">{formatDate(event.date)} {formatTime(event.date)}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${impact?.bg} ${impact?.text}`}>
                    {impact?.label}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Category filters */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={14} className="text-gray-500" />
          <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">Filtrer par categorie</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(CATEGORY_CONFIG).map(([key, config]) => {
            const isActive = activeFilters.has(key)
            return (
              <button
                key={key}
                onClick={() => toggleFilter(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {config.icon}
                {config.label}
              </button>
            )
          })}
          {activeFilters.size > 0 && (
            <button
              onClick={() => setActiveFilters(new Set())}
              className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-300 transition"
            >
              Effacer filtres
            </button>
          )}
        </div>
      </div>

      {/* Events timeline grouped by month */}
      {filteredEvents.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
          <CalendarDays size={48} className="text-gray-700 mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2 text-gray-400">
            Aucun evenement
          </h3>
          <p className="text-gray-600 text-sm">
            Aucun evenement economique ne correspond aux filtres selectionnes.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedEvents).map(([monthLabel, monthEvents]) => (
            <div key={monthLabel}>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 px-1">
                {monthLabel}
              </h3>
              <div className="space-y-2">
                {monthEvents.map((event, i) => {
                  const impact = IMPACT_STYLES[event.impact]
                  const cat = CATEGORY_CONFIG[event.category]
                  const imminent = isWithin48h(event.date)
                  const today = isToday(event.date)

                  return (
                    <div
                      key={`${event.date}-${i}`}
                      className={`bg-gray-900 rounded-xl border overflow-hidden transition ${
                        today
                          ? 'border-yellow-500/40 bg-yellow-500/5'
                          : imminent
                            ? 'border-blue-500/30 bg-blue-500/5'
                            : 'border-gray-800 hover:border-gray-700'
                      }`}
                    >
                      <div className="flex items-start gap-4 p-4">
                        {/* Date column */}
                        <div className="flex-shrink-0 w-16 text-center">
                          <div className="text-2xl font-bold text-gray-200">
                            {new Date(event.date).getDate()}
                          </div>
                          <div className="text-xs text-gray-500 uppercase">
                            {new Date(event.date).toLocaleDateString('fr-FR', { weekday: 'short' })}
                          </div>
                          <div className="text-xs text-gray-600 mt-0.5">
                            {formatTime(event.date)}
                          </div>
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {/* Category icon */}
                            <span className={`flex items-center gap-1 text-xs font-medium ${cat?.color || 'text-gray-400'}`}>
                              {cat?.icon}
                              {cat?.label}
                            </span>

                            {/* Impact badge */}
                            <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${impact?.bg} ${impact?.text}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${impact?.dot}`} />
                              {impact?.label}
                            </span>

                            {/* Countdown */}
                            <span className={`text-xs ml-auto ${
                              today ? 'text-yellow-400 font-medium' : imminent ? 'text-blue-400' : 'text-gray-600'
                            }`}>
                              {daysUntil(event.date)}
                            </span>
                          </div>

                          <h4 className="font-semibold text-sm text-gray-200 mb-1">
                            {event.title}
                          </h4>
                          <p className="text-xs text-gray-500 leading-relaxed">
                            {event.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
