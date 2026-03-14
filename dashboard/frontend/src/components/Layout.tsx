import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BarChart3, Settings, History, LogOut, Brain, Terminal, Menu, X, User, Users } from 'lucide-react'
import AltiorLogo from '../assets/AltiorLogo'
import type { UserInfo } from '../App'

interface LayoutProps {
  children: React.ReactNode
  onLogout: () => void
  userInfo?: UserInfo | null
}

const NAV = [
  { to: '/', label: 'Dashboard', icon: BarChart3 },
  { to: '/trades', label: 'Trades', icon: History },
  { to: '/ai', label: 'Analyse IA', icon: Brain },
  { to: '/logs', label: 'Logs', icon: Terminal },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/users', label: 'Utilisateurs', icon: Users, adminOnly: true },
]

export default function Layout({ children, onLogout, userInfo }: LayoutProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const sidebar = (
    <>
      <div className="px-5 py-5 flex items-center gap-3">
        <AltiorLogo size={44} className="text-blue-400 shrink-0" />
        <div>
          <p className="text-[10px] text-gray-500 font-medium tracking-wider uppercase">Holding</p>
          <p className="text-[10px] text-gray-600 mt-0.5">Auto-Trade Bot</p>
        </div>
      </div>

      <nav className="flex-1 px-4 space-y-1">
        {NAV.filter(item => !item.adminOnly || userInfo?.role === 'admin').map(({ to, label, icon: Icon }) => {
          const active = location.pathname === to
          return (
            <Link
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
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

      {/* User info + logout */}
      <div className="p-4 border-t border-gray-800 space-y-3">
        {userInfo && (
          <div className="flex items-center gap-2 text-xs">
            <User size={14} className="text-gray-500" />
            <span className="text-gray-400">{userInfo.username}</span>
            <span className="ml-auto px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 text-[10px] uppercase">
              {userInfo.role}
            </span>
          </div>
        )}
        <button
          onClick={onLogout}
          className="flex items-center gap-2 text-gray-500 hover:text-red-400 text-sm transition"
        >
          <LogOut size={16} />
          Logout
        </button>
      </div>
    </>
  )

  return (
    <div className="flex h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 bg-gray-900 border-r border-gray-800 flex-col shrink-0">
        {sidebar}
      </aside>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <AltiorLogo size={32} className="text-blue-400" />
          <span className="text-xs text-gray-500 font-medium tracking-wider uppercase">Altior</span>
        </div>
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-gray-400 hover:text-white p-1"
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="md:hidden fixed top-0 left-0 bottom-0 z-50 w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
            {sidebar}
          </aside>
        </>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-auto p-4 md:p-8 pt-16 md:pt-8">{children}</main>
    </div>
  )
}
