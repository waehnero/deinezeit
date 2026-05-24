import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard, Database, Users, User, LogOut, Menu, X,
  ChevronRight, Clock, Settings2, HardDrive
} from 'lucide-react'
import { useSettings } from '../contexts/SettingsContext'
import { useAuth } from '../contexts/AuthContext'


const NAV_ITEMS = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/zeiterfassung',icon: Clock,           label: 'Zeiterfassung' },
  { to: '/masterdata',   icon: Database,        label: 'Stammdaten' },
  { to: '/datacenter',   icon: HardDrive,       label: 'Datacenter' },
  { to: '/users',        icon: Users,           label: 'Benutzer' },
]

export default function Layout({ children }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const { isAdmin } = useAuth()
  const { settings } = useSettings()

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login')
  }

  const logoUrl = settings.logo_url || null

  const companyName = settings.company_name || 'DeineZeit'

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo / Firmenname */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-neutral-100">
        {logoUrl ? (
          <img src={logoUrl} alt="Logo" className="w-8 h-8 object-contain flex-shrink-0" />
        ) : (
          <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">
              {companyName.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}
        <div className="min-w-0">
          <span className="font-semibold text-neutral-900 text-sm block truncate">{companyName}</span>
          {settings.app_subtitle && (
            <span className="text-[10px] text-neutral-400 block truncate">{settings.app_subtitle}</span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="text-xs font-medium text-neutral-400 uppercase tracking-wider px-2 pb-2">Menü</p>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group ${
                isActive ? 'bg-primary-50 text-primary-700' : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} className={isActive ? 'text-primary-600' : 'text-neutral-400 group-hover:text-neutral-600'} />
                <span>{label}</span>
                {isActive && <ChevronRight size={14} className="ml-auto text-primary-400" />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Unterer Bereich */}
      <div className="px-3 pb-4 border-t border-neutral-100 pt-3 space-y-0.5">
        {isAdmin && (
          <NavLink to="/settings" onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group ${
                isActive ? 'bg-primary-50 text-primary-700' : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Settings2 size={17} className={isActive ? 'text-primary-600' : 'text-neutral-400 group-hover:text-neutral-600'} />
                <span>Einstellungen</span>
              </>
            )}
          </NavLink>
        )}
        <NavLink to="/profile" onClick={() => setMobileOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group ${
              isActive ? 'bg-primary-50 text-primary-700' : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <User size={17} className={isActive ? 'text-primary-600' : 'text-neutral-400 group-hover:text-neutral-600'} />
              <span>{t('nav.profile')}</span>
            </>
          )}
        </NavLink>
        <button onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-neutral-600 hover:bg-red-50 hover:text-red-600 transition-all duration-150 group">
          <LogOut size={17} className="text-neutral-400 group-hover:text-red-500" />
          <span>{t('auth.logout')}</span>
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-neutral-50 overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-56 bg-white border-r border-neutral-200 flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-neutral-900/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-56 bg-white shadow-xl z-50">
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Hauptbereich */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile Header */}
        <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-neutral-200">
          <div className="flex items-center gap-3">
            {logoUrl ? (
              <img src={logoUrl} alt="Logo" className="w-7 h-7 object-contain"
                onError={e => { e.target.style.display='none' }} />
            ) : (
              <div className="w-7 h-7 bg-primary-500 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-xs">{companyName.slice(0, 2).toUpperCase()}</span>
              </div>
            )}
            <span className="font-semibold text-neutral-900 text-sm">{companyName}</span>
          </div>
          <button onClick={() => setMobileOpen(!mobileOpen)} className="p-1.5 rounded-lg hover:bg-neutral-100 text-neutral-600">
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
