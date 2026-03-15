import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BarChart3, Settings, History, LogOut, Brain, Terminal, Menu, X, User, Users, TrendingUp, BookOpen, Shield, HeartPulse, GitCompareArrows, Zap, Globe, Bell, BellOff, FlaskConical, BellRing, Repeat, Copy, FileBarChart, Grid3X3, Sun, Moon, Languages, PieChart, ShoppingCart, Newspaper, CalendarDays, Lock } from 'lucide-react'
import { usePushSubscription } from '../hooks/useNotifications'
import { useTheme } from '../hooks/useTheme'
import { useTranslation } from '../i18n/useTranslation'
import AltiorLogo from '../assets/AltiorLogo'
import type { UserInfo } from '../App'

interface LayoutProps {
  children: React.ReactNode
  onLogout: () => void
  userInfo?: UserInfo | null
  token?: string
}

const NAV = [
  { to: '/', labelKey: 'nav.dashboard', icon: BarChart3 },
  { to: '/trades', labelKey: 'nav.trades', icon: History },
  { to: '/analytics', labelKey: 'nav.analytics', icon: TrendingUp },
  { to: '/compare', labelKey: 'nav.comparison', icon: GitCompareArrows },
  { to: '/journal', labelKey: 'nav.journal', icon: BookOpen },
  { to: '/strategies', labelKey: 'nav.strategies', icon: Zap },
  { to: '/polymarket', labelKey: 'nav.polymarket', icon: Globe },
  { to: '/ai', labelKey: 'nav.ai', icon: Brain },
  { to: '/logs', labelKey: 'nav.logs', icon: Terminal },
  { to: '/backtest', labelKey: 'nav.backtest', icon: FlaskConical },
  { to: '/alerts', labelKey: 'nav.alerts', icon: BellRing },
  { to: '/dca', labelKey: 'nav.dca', icon: Repeat },
  { to: '/copy-trading', labelKey: 'nav.copy', icon: Copy },
  { to: '/reports', labelKey: 'nav.reports', icon: FileBarChart },
  { to: '/correlation', labelKey: 'nav.correlation', icon: Grid3X3 },
  { to: '/portfolio', labelKey: 'nav.portfolio', icon: PieChart },
  { to: '/orders', labelKey: 'nav.orders', icon: ShoppingCart },
  { to: '/market-journal', labelKey: 'nav.market_journal', icon: Newspaper },
  { to: '/calendar', labelKey: 'nav.calendar', icon: CalendarDays },
  { to: '/health', labelKey: 'nav.health', icon: HeartPulse },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
  { to: '/users', labelKey: 'nav.users', icon: Users, adminOnly: true },
  { to: '/audit', labelKey: 'nav.audit', icon: Shield, adminOnly: true },
  { to: '/permissions', labelKey: 'nav.permissions', icon: Lock, adminOnly: true },
]

export default function Layout({ children, onLogout, userInfo, token }: LayoutProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { isSubscribed, isSupported, subscribe, unsubscribe } = usePushSubscription(token || '')
  const { theme, toggleTheme } = useTheme()
  const { t, lang, switchLang } = useTranslation()

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
        {NAV.filter(item => !item.adminOnly || userInfo?.role === 'admin').map(({ to, labelKey, icon: Icon }) => {
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
              {t(labelKey)}
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

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-300 transition w-full"
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          {theme === 'dark' ? t('theme.light') : t('theme.dark')}
        </button>

        {/* Language toggle */}
        <button
          onClick={switchLang}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-300 transition w-full"
        >
          <Languages size={16} />
          {lang === 'fr' ? 'EN' : 'FR'}
        </button>

        {isSupported && (
          <button
            onClick={isSubscribed ? unsubscribe : subscribe}
            className={`flex items-center gap-2 text-sm transition w-full ${
              isSubscribed ? 'text-blue-400 hover:text-blue-300' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {isSubscribed ? <BellOff size={16} /> : <Bell size={16} />}
            {isSubscribed ? t('common.alerts_active') : t('common.enable_alerts')}
          </button>
        )}
        <button
          onClick={onLogout}
          className="flex items-center gap-2 text-gray-500 hover:text-red-400 text-sm transition"
        >
          <LogOut size={16} />
          {t('common.logout')}
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
      <main className="flex-1 overflow-auto p-4 md:p-8 pt-16 md:pt-8 pb-16 md:pb-0">{children}</main>

      {/* Mobile bottom navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-gray-900 border-t border-gray-800 flex justify-around py-2">
        {[
          { to: '/', icon: BarChart3, label: 'Home' },
          { to: '/trades', icon: History, label: 'Trades' },
          { to: '/alerts', icon: BellRing, label: 'Alertes' },
          { to: '/portfolio', icon: PieChart, label: 'Portfolio' },
          { to: '/settings', icon: Settings, label: 'Settings' },
        ].map(({ to, icon: Icon, label }) => (
          <Link key={to} to={to} className={`flex flex-col items-center gap-0.5 px-3 py-1 ${location.pathname === to ? 'text-blue-400' : 'text-gray-500'}`}>
            <Icon size={20} />
            <span className="text-[10px]">{label}</span>
          </Link>
        ))}
      </nav>
    </div>
  )
}
