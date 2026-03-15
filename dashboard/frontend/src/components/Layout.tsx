import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  BarChart3, Settings, History, LogOut, Brain, Terminal, Menu, X, Users,
  TrendingUp, BookOpen, Shield, HeartPulse, GitCompareArrows, Zap, Globe,
  Bell, BellOff, FlaskConical, BellRing, Repeat, Copy, FileBarChart, Grid3X3,
  Sun, Moon, PieChart, ShoppingCart, Newspaper, CalendarDays, Lock,
  ChevronDown,
} from 'lucide-react'
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

interface NavItem {
  to: string
  labelKey: string
  icon: typeof BarChart3
  adminOnly?: boolean
}

interface NavSection {
  titleKey: string
  items: NavItem[]
  collapsible?: boolean
}

const NAV_SECTIONS: NavSection[] = [
  {
    titleKey: '',
    items: [
      { to: '/', labelKey: 'nav.dashboard', icon: BarChart3 },
      { to: '/portfolio', labelKey: 'nav.portfolio', icon: PieChart },
      { to: '/trades', labelKey: 'nav.trades', icon: History },
      { to: '/orders', labelKey: 'nav.orders', icon: ShoppingCart },
    ],
  },
  {
    titleKey: 'nav.section.analysis',
    collapsible: true,
    items: [
      { to: '/analytics', labelKey: 'nav.analytics', icon: TrendingUp },
      { to: '/compare', labelKey: 'nav.comparison', icon: GitCompareArrows },
      { to: '/correlation', labelKey: 'nav.correlation', icon: Grid3X3 },
      { to: '/backtest', labelKey: 'nav.backtest', icon: FlaskConical },
      { to: '/reports', labelKey: 'nav.reports', icon: FileBarChart },
    ],
  },
  {
    titleKey: 'nav.section.intelligence',
    collapsible: true,
    items: [
      { to: '/ai', labelKey: 'nav.ai', icon: Brain },
      { to: '/polymarket', labelKey: 'nav.polymarket', icon: Globe },
      { to: '/market-journal', labelKey: 'nav.market_journal', icon: Newspaper },
      { to: '/calendar', labelKey: 'nav.calendar', icon: CalendarDays },
    ],
  },
  {
    titleKey: 'nav.section.automation',
    collapsible: true,
    items: [
      { to: '/strategies', labelKey: 'nav.strategies', icon: Zap },
      { to: '/alerts', labelKey: 'nav.alerts', icon: BellRing },
      { to: '/dca', labelKey: 'nav.dca', icon: Repeat },
      { to: '/copy-trading', labelKey: 'nav.copy', icon: Copy },
      { to: '/journal', labelKey: 'nav.journal', icon: BookOpen },
    ],
  },
  {
    titleKey: 'nav.section.system',
    collapsible: true,
    items: [
      { to: '/settings', labelKey: 'nav.settings', icon: Settings },
      { to: '/health', labelKey: 'nav.health', icon: HeartPulse },
      { to: '/logs', labelKey: 'nav.logs', icon: Terminal },
      { to: '/users', labelKey: 'nav.users', icon: Users, adminOnly: true },
      { to: '/audit', labelKey: 'nav.audit', icon: Shield, adminOnly: true },
      { to: '/permissions', labelKey: 'nav.permissions', icon: Lock, adminOnly: true },
    ],
  },
]

export default function Layout({ children, onLogout, userInfo, token }: LayoutProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { isSubscribed, isSupported, subscribe, unsubscribe } = usePushSubscription(token || '')
  const { theme, toggleTheme } = useTheme()
  const { t, lang, switchLang } = useTranslation()

  // Track collapsed sections (default: all expanded)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const toggleSection = (key: string) =>
    setCollapsed(prev => ({ ...prev, [key]: !prev[key] }))

  // Check if any item in a section is active (auto-expand if so)
  const isSectionActive = (items: NavItem[]) =>
    items.some(item => location.pathname === item.to)

  const sidebar = (
    <>
      {/* Logo */}
      <div className="px-5 py-4 flex items-center gap-3 border-b border-gray-800/50">
        <AltiorLogo size={36} className="text-blue-400 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white tracking-tight truncate">Altior Holding</p>
          <p className="text-[10px] text-gray-500 font-medium tracking-wider uppercase">Auto-Trade</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-1 scrollbar-thin">
        {NAV_SECTIONS.map((section, sIdx) => {
          const visibleItems = section.items.filter(
            item => !item.adminOnly || userInfo?.role === 'admin'
          )
          if (visibleItems.length === 0) return null

          const sectionKey = section.titleKey || `s${sIdx}`
          const isCollapsed = collapsed[sectionKey] && !isSectionActive(visibleItems)

          return (
            <div key={sectionKey}>
              {/* Section header */}
              {section.titleKey && (
                <button
                  onClick={() => section.collapsible && toggleSection(sectionKey)}
                  className="flex items-center justify-between w-full px-3 pt-4 pb-1.5 group"
                >
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
                    {t(section.titleKey)}
                  </span>
                  {section.collapsible && (
                    <ChevronDown
                      size={12}
                      className={`text-gray-600 transition-transform duration-200 ${
                        isCollapsed ? '-rotate-90' : ''
                      }`}
                    />
                  )}
                </button>
              )}

              {/* Items */}
              {!isCollapsed && visibleItems.map(({ to, labelKey, icon: Icon }) => {
                const active = location.pathname === to
                return (
                  <Link
                    key={to}
                    to={to}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center gap-3 px-3 py-1.5 rounded-lg text-[13px] transition-all duration-150 ${
                      active
                        ? 'bg-blue-500/15 text-blue-400 font-medium'
                        : 'text-gray-400 hover:bg-gray-800/70 hover:text-gray-200'
                    }`}
                  >
                    <Icon size={16} className={active ? 'text-blue-400' : 'text-gray-500'} />
                    {t(labelKey)}
                  </Link>
                )
              })}
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-800/50 space-y-1.5">
        {/* User info */}
        {userInfo && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800/40">
            <div className="w-7 h-7 rounded-full bg-blue-500/20 flex items-center justify-center">
              <span className="text-blue-400 text-xs font-bold uppercase">
                {userInfo.username.charAt(0)}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-300 font-medium truncate">{userInfo.username}</p>
              <p className="text-[10px] text-gray-500 uppercase">{userInfo.role}</p>
            </div>
          </div>
        )}

        {/* Quick actions row */}
        <div className="flex items-center gap-1 px-1">
          <button
            onClick={toggleTheme}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition text-xs"
            title={theme === 'dark' ? t('theme.light') : t('theme.dark')}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
          <button
            onClick={switchLang}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition text-xs font-medium"
            title={lang === 'fr' ? 'Switch to English' : 'Passer en Francais'}
          >
            {lang === 'fr' ? 'EN' : 'FR'}
          </button>
          {isSupported && (
            <button
              onClick={isSubscribed ? unsubscribe : subscribe}
              className={`flex-1 flex items-center justify-center py-1.5 rounded-md transition text-xs ${
                isSubscribed ? 'text-blue-400 hover:text-blue-300' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
              }`}
              title={isSubscribed ? t('common.alerts_active') : t('common.enable_alerts')}
            >
              {isSubscribed ? <BellOff size={14} /> : <Bell size={14} />}
            </button>
          )}
          <button
            onClick={onLogout}
            className="flex-1 flex items-center justify-center py-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-gray-800/50 transition text-xs"
            title={t('common.logout')}
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </>
  )

  return (
    <div className="flex h-screen bg-gray-950">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-60 bg-gray-900 border-r border-gray-800/50 flex-col shrink-0">
        {sidebar}
      </aside>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800/50 flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <AltiorLogo size={28} className="text-blue-400" />
          <span className="text-sm font-semibold text-white">Altior</span>
        </div>
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-gray-800 transition"
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="md:hidden fixed top-0 left-0 bottom-0 z-50 w-64 bg-gray-900 border-r border-gray-800/50 flex flex-col shadow-2xl">
            {sidebar}
          </aside>
        </>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-auto p-4 md:p-8 pt-16 md:pt-8 pb-20 md:pb-8">{children}</main>

      {/* Mobile bottom navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-gray-900/95 backdrop-blur-sm border-t border-gray-800/50 flex justify-around py-1.5 safe-bottom">
        {[
          { to: '/', icon: BarChart3, label: 'Home' },
          { to: '/portfolio', icon: PieChart, label: 'Portfolio' },
          { to: '/trades', icon: History, label: 'Trades' },
          { to: '/alerts', icon: BellRing, label: 'Alertes' },
          { to: '/settings', icon: Settings, label: 'Settings' },
        ].map(({ to, icon: Icon, label }) => {
          const active = location.pathname === to
          return (
            <Link
              key={to}
              to={to}
              className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg transition ${
                active ? 'text-blue-400' : 'text-gray-500 active:text-gray-300'
              }`}
            >
              <Icon size={20} strokeWidth={active ? 2.5 : 1.5} />
              <span className={`text-[10px] ${active ? 'font-medium' : ''}`}>{label}</span>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
