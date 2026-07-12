import { useState, useEffect } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard, Database, Users, User, LogOut, Menu, X,
  ChevronRight, ChevronDown, Clock, Settings2, HardDrive, Receipt, GanttChartSquare,
  PanelLeftClose, PanelLeftOpen, ListTodo, Megaphone, Moon
} from 'lucide-react'
import { toggleDark } from '../utils/anzeige'
import { useSettings } from '../contexts/SettingsContext'
import { useAuth } from '../contexts/AuthContext'
import { masterdataApi } from '../services/api'
import UpdateBanner from './UpdateBanner'
import CommandPalette from './CommandPalette'


// module = Schlüssel der Modulrechte (backend/app/core/modules.py);
// der Admin schaltet Module pro Benutzer in der Benutzerverwaltung frei.
const NAV_ITEMS = [
  { to: '/dashboard',    icon: LayoutDashboard,  label: 'Dashboard',     module: 'dashboard' },
  { to: '/zeiterfassung',icon: Clock,            label: 'Zeiterfassung', module: 'zeiterfassung' },
  { to: '/aufgaben',     icon: ListTodo,         label: 'Aufgaben',      module: 'aufgaben' },
  { to: '/projekte',     icon: GanttChartSquare, label: 'Projekte',      module: 'projekte' },
  { to: '/invoices',     icon: Receipt,          label: 'Verkauf',       module: 'verkauf' },
  { to: '/postecke',     icon: Megaphone,        label: 'Postecke',      module: 'postecke' },
  { to: '/masterdata',   icon: Database,         label: 'Stammdaten',    module: 'stammdaten' },
  { to: '/datacenter',   icon: HardDrive,        label: 'Datacenter',    module: 'datacenter' },
]

// Startziel eines Benutzers: Dashboard, sonst erstes freigeschaltetes Modul
export function homeRoute(hasModule) {
  const first = NAV_ITEMS.find(item => hasModule(item.module))
  return first ? first.to : '/profile'
}

export default function Layout({ children }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  // Desktop-Sidebar eingeklappt (nur Symbole). Wahl in localStorage merken.
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar_collapsed') === '1' } catch { return false }
  })
  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem('sidebar_collapsed', next ? '1' : '0') } catch {}
      return next
    })
  }

  const { isAdmin, hasModule } = useAuth()
  const { settings } = useSettings()
  const location = useLocation()

  // Stammdaten-Untermenü: Entity-Typen (Kontakte, Artikel, …) direkt in der
  // Sidebar aufklappen; Klick auf einen Typ öffnet rechts die Typ-Ansicht.
  const [mdTypes, setMdTypes] = useState([])
  useEffect(() => {
    if (!hasModule('stammdaten')) return
    masterdataApi.listTypes()
      .then(res => setMdTypes(res.data || []))
      .catch(() => setMdTypes([]))
    // Bei Routenwechsel innerhalb der Stammdaten neu laden (neue Typen sichtbar)
  }, [hasModule('stammdaten'), location.pathname.startsWith('/masterdata')])
  const mdOpen = location.pathname.startsWith('/masterdata')

  // Einträge der ⌘K-Befehlspalette: Module, Stammdaten-Typen, Aktionen
  const paletteItems = [
    ...NAV_ITEMS.filter(item => hasModule(item.module))
      .map(item => ({ label: item.label, icon: item.icon, to: item.to, group: 'Module' })),
    ...mdTypes.map(t2 => ({ label: t2.name, icon: Database, to: `/masterdata/${t2.slug}`, group: 'Stammdaten' })),
    ...(isAdmin ? [{ label: 'Einstellungen', icon: Settings2, to: '/settings', group: 'Aktionen' }] : []),
    { label: 'Mein Profil', icon: User, to: '/profile', group: 'Aktionen' },
    { label: 'Dunkelmodus umschalten', icon: Moon, action: () => toggleDark(), group: 'Aktionen' },
    { label: 'Abmelden', icon: LogOut, action: () => handleLogout(), group: 'Aktionen' },
  ]

  // Nur freigeschaltete Module im Menü zeigen
  const navItems = NAV_ITEMS.filter(item => hasModule(item.module))
  const home = navItems.length ? navItems[0].to : '/profile'

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login')
  }

  // Sidebar-Logo: wahlweise das Original-Logo oder das Favicon (Einstellungen → Allgemein)
  const logoUrl = (settings.sidebar_logo_source === 'favicon' && settings.logo_favicon_url)
    ? settings.logo_favicon_url
    : (settings.logo_url || null)

  const companyName = settings.company_name || 'DeineZeit'

  const SidebarContent = ({ mini = false }) => (
    <div className="flex flex-col h-full">
      {/* Logo / Firmenname – führt zum Dashboard */}
      <button
        onClick={() => { navigate(home); setMobileOpen(false) }}
        className={`flex items-center gap-3 border-b border-sidebar-border/50 w-full text-left hover:bg-sidebar-hover transition-colors ${
          mini ? 'justify-center px-2 py-4' : 'px-4 py-5'
        }`}
        title="Zur Startseite"
      >
        {logoUrl ? (
          <img src={logoUrl} alt="Logo" className="w-8 h-8 object-contain flex-shrink-0" />
        ) : (
          <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">
              {companyName.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}
        {!mini && (
          <div className="min-w-0">
            <span className="font-semibold text-sidebar-text-hover text-sm block truncate">{companyName}</span>
            {settings.app_subtitle && (
              <span className="text-[10px] text-sidebar-text/70 block truncate">{settings.app_subtitle}</span>
            )}
          </div>
        )}
      </button>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {!mini && (
          <p className="text-xs font-medium text-sidebar-text/60 uppercase tracking-wider px-2 pb-2">Menü</p>
        )}
        {navItems.map(({ to, icon: Icon, label, module }) => (
          <div key={to}>
            <NavLink to={to} onClick={() => setMobileOpen(false)}
              title={mini ? label : undefined}
              end={module === 'stammdaten'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150 group ${
                  mini ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'
                } ${
                  isActive ? 'bg-sidebar-active text-sidebar-active-text' : 'text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-hover'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={17} className={isActive ? 'text-sidebar-active-text' : 'text-sidebar-text/70 group-hover:text-sidebar-text-hover'} />
                  {!mini && <span>{label}</span>}
                  {!mini && module === 'stammdaten' && mdTypes.length > 0 && (
                    mdOpen
                      ? <ChevronDown size={14} className="ml-auto text-sidebar-text/60" />
                      : <ChevronRight size={14} className="ml-auto text-sidebar-text/60" />
                  )}
                  {!mini && module !== 'stammdaten' && isActive && <ChevronRight size={14} className="ml-auto text-primary-400" />}
                </>
              )}
            </NavLink>

            {/* Stammdaten-Untermenü: Typen (Kontakte, Artikel, …) aufgeklappt,
                sobald man sich im Stammdaten-Bereich befindet */}
            {module === 'stammdaten' && !mini && mdOpen && mdTypes.length > 0 && (
              <div className="ml-8 mt-0.5 space-y-0.5">
                {mdTypes.map(t2 => (
                  <NavLink key={t2.slug} to={`/masterdata/${t2.slug}`} onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                        isActive
                          ? 'bg-sidebar-active text-sidebar-active-text font-medium'
                          : 'text-sidebar-text/80 hover:bg-sidebar-hover hover:text-sidebar-text-hover'
                      }`
                    }
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60 flex-shrink-0" />
                    <span className="truncate">{t2.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Unterer Bereich */}
      <div className="px-3 pb-4 border-t border-sidebar-border/50 pt-3 space-y-0.5">
        {isAdmin && (
          <NavLink to="/settings" onClick={() => setMobileOpen(false)}
            title={mini ? 'Einstellungen' : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150 group ${
                mini ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'
              } ${
                isActive ? 'bg-sidebar-active text-sidebar-active-text' : 'text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-hover'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Settings2 size={17} className={isActive ? 'text-sidebar-active-text' : 'text-sidebar-text/70 group-hover:text-sidebar-text-hover'} />
                {!mini && <span>Einstellungen</span>}
              </>
            )}
          </NavLink>
        )}
        <NavLink to="/profile" onClick={() => setMobileOpen(false)}
          title={mini ? t('nav.profile') : undefined}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150 group ${
              mini ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'
            } ${
              isActive ? 'bg-sidebar-active text-sidebar-active-text' : 'text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-hover'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <User size={17} className={isActive ? 'text-sidebar-active-text' : 'text-sidebar-text/70 group-hover:text-sidebar-text-hover'} />
              {!mini && <span>{t('nav.profile')}</span>}
            </>
          )}
        </NavLink>
        <button onClick={handleLogout}
          title={mini ? t('auth.logout') : undefined}
          className={`w-full flex items-center gap-3 rounded-lg text-sm font-medium text-sidebar-text hover:bg-red-50 hover:text-red-600 transition-all duration-150 group ${
            mini ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'
          }`}>
          <LogOut size={17} className="text-sidebar-text/70 group-hover:text-red-500" />
          {!mini && <span>{t('auth.logout')}</span>}
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-neutral-50 overflow-hidden">
      <UpdateBanner />
      {/* Desktop Sidebar */}
      <aside style={{ paddingTop: 'env(safe-area-inset-top)', paddingLeft: 'env(safe-area-inset-left)' }}
        className={`hidden lg:flex flex-col bg-sidebar border-r border-sidebar-border flex-shrink-0 relative transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-56'
      }`}>
        <SidebarContent mini={collapsed} />
        {/* Ein-/Ausklappen */}
        <button
          onClick={toggleCollapsed}
          title={collapsed ? 'Menü ausklappen' : 'Menü einklappen'}
          className="absolute -right-3 top-20 z-10 w-6 h-6 bg-surface border border-neutral-200 rounded-full flex items-center justify-center text-neutral-400 hover:text-primary-600 hover:border-primary-300 shadow-sm transition-colors"
        >
          {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        </button>
      </aside>

      {/* Mobile Overlay — liegt ÜBER der Bottom-Tab-Bar (z-40), damit auch
          die unteren Menüpunkte (Profil, Abmelden) erreichbar sind */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <div className="absolute inset-0 bg-neutral-900/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-56 bg-sidebar shadow-xl z-50 overflow-y-auto"
            style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Hauptbereich */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile Header – berücksichtigt iOS Safe Area (Notch/Statusleiste) */}
        <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-surface border-b border-neutral-200"
          style={{ paddingTop: 'calc(0.75rem + env(safe-area-inset-top))' }}>
          <button onClick={() => navigate('/dashboard')} className="flex items-center gap-3" title="Zum Dashboard">
            {logoUrl ? (
              <img src={logoUrl} alt="Logo" className="w-7 h-7 object-contain"
                onError={e => { e.target.style.display='none' }} />
            ) : (
              <div className="w-7 h-7 bg-primary-500 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-xs">{companyName.slice(0, 2).toUpperCase()}</span>
              </div>
            )}
            <span className="font-semibold text-neutral-900 text-sm">{companyName}</span>
          </button>
          <button onClick={() => setMobileOpen(!mobileOpen)} className="p-1.5 rounded-lg hover:bg-neutral-100 text-neutral-600">
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto"
          style={{ paddingLeft: 'env(safe-area-inset-left)', paddingRight: 'env(safe-area-inset-right)' }}>
          {/* Einheitlicher Seitenrahmen (Design-Verfassung, Regel 3/4):
              gleiche maximale Breite und gleiche Außenabstände für ALLE
              Module, responsive auf iPhone/iPad/Desktop. Seiten definieren
              keine eigenen Außenbreiten/-abstände mehr. Unten am Handy Platz
              für die Bottom-Tab-Bar. */}
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 pt-4 sm:pt-6 pb-24 lg:pb-6">
            {children}
          </div>
        </main>

        {/* Bottom-Tab-Bar (nur mobil; Design-Verfassung, Regel 4):
            maximal 5 Plätze — die ersten 4 freigeschalteten Module plus
            „Mehr" (öffnet das vollständige Menü). Reihenfolge = Modulrechte. */}
        <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-sidebar border-t border-sidebar-border flex items-stretch justify-around"
          style={{
            paddingBottom: 'env(safe-area-inset-bottom)',
            paddingLeft:   'env(safe-area-inset-left)',
            paddingRight:  'env(safe-area-inset-right)',
          }}>
          {navItems.slice(0, 4).map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-0.5 flex-1 py-2 min-h-[56px] text-[10px] font-medium transition-colors ${
                  isActive ? 'text-sidebar-active-text' : 'text-sidebar-text/70'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span className={`px-3 py-0.5 rounded-full ${isActive ? 'bg-sidebar-active' : ''}`}>
                    <Icon size={19} />
                  </span>
                  <span className="truncate max-w-[72px]">{label}</span>
                </>
              )}
            </NavLink>
          ))}
          <button onClick={() => setMobileOpen(true)}
            className="flex flex-col items-center justify-center gap-0.5 flex-1 py-2 min-h-[56px] text-[10px] font-medium text-sidebar-text/70">
            <span className="px-3 py-0.5"><Menu size={19} /></span>
            <span>Mehr</span>
          </button>
        </nav>
      </div>

      {/* ⌘K-Befehlspalette (global, öffnet per Cmd/Ctrl+K oder Suchknopf) */}
      <CommandPalette items={paletteItems} />
    </div>
  )
}
