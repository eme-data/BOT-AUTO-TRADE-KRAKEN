import { Link, useLocation } from 'react-router-dom'
import { BarChart3, Settings, History, LogOut, Brain, Terminal } from 'lucide-react'
import AltiorLogo from '../assets/AltiorLogo'

interface LayoutProps {
  children: React.ReactNode
  onLogout: () => void
}

const NAV = [
  { to: '/', label: 'Dashboard', icon: BarChart3 },
  { to: '/trades', label: 'Trades', icon: History },
  { to: '/ai', label: 'Analyse IA', icon: Brain },
  { to: '/logs', label: 'Logs', icon: Terminal },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout({ children, onLogout }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="px-5 py-5 flex items-center gap-3">
          <AltiorLogo size={44} className="text-blue-400 shrink-0" />
          <div>
            <p className="text-[10px] text-gray-500 font-medium tracking-wider uppercase">Holding</p>
            <p className="text-[10px] text-gray-600 mt-0.5">Auto-Trade Bot</p>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition ${
                  active
                    ? 'bg-blue-600/20 text-blue-400'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
              >
                <Icon size={18} />
                {label}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <button
            onClick={onLogout}
            className="flex items-center gap-2 text-gray-500 hover:text-red-400 text-sm transition"
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  )
}
