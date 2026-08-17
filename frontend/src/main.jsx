import React, { Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { Loader2 } from 'lucide-react'
import './i18n'
import './index.css'
import { initPrefs } from './utils/anzeige'

import { SettingsProvider } from './contexts/SettingsContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import LoginPage from './pages/LoginPage'
import SetupPage from './pages/SetupPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import DashboardPage from './pages/DashboardPage'
import MasterDataOverview from './pages/MasterDataOverview'
import MasterDataDetail from './pages/MasterDataDetail'
import ProfilePage from './pages/ProfilePage'
import UserManagementPage from './pages/UserManagementPage'
import ZeiterfassungPage from './pages/ZeiterfassungPage'
import ZeiterfassungFelder from './pages/ZeiterfassungFelder'
import SettingsPage from './pages/SettingsPage'
import DatacenterPage from './pages/DatacenterPage'
import InvoicePage from './pages/InvoicePage'
import InvoiceFormPage from './pages/InvoiceFormPage'
import InvoiceBookPage from './pages/InvoiceBookPage'
import OpenItemsPage from './pages/OpenItemsPage'
import MonatsabschlussPage from './pages/MonatsabschlussPage'
import MahnlaufPage from './pages/MahnlaufPage'
import AuswertungenPage from './pages/AuswertungenPage'
import BuchhaltungPage from './pages/BuchhaltungPage'
import KontenplanPage from './pages/KontenplanPage'
import EingangsrechnungenPage from './pages/EingangsrechnungenPage'
import ProjektplanPage from './pages/ProjektplanPage'
import ProjektplanDetailPage from './pages/ProjektplanDetailPage'
import ProjekteEinstellungen from './pages/ProjekteEinstellungen'
import AufgabenPage from './pages/AufgabenPage'
import PosteckePage from './pages/PosteckePage'
import Layout, { homeRoute } from './components/Layout'

const AuthSpinner = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 size={28} className="animate-spin text-primary-400" />
  </div>
)

/**
 * Zugang nur für angemeldete Benutzer.
 *
 * Vorher wurde geprüft, ob ein Token in localStorage liegt. Das geht nicht
 * mehr — der Access-Token lebt im Arbeitsspeicher und ist nach jedem Neuladen
 * weg, während die Sitzung im httpOnly-Cookie weiterbesteht. Ohne das Warten
 * auf `loadingAuth` würde jeder Seiten-Neuaufbau (F5, PWA-Start, Öffnen eines
 * Lesezeichens) fälschlich auf die Anmeldemaske führen, obwohl der Benutzer
 * angemeldet ist.
 */
function ProtectedRoute({ children }) {
  const { istAngemeldet, loadingAuth } = useAuth()
  if (loadingAuth) return <AuthSpinner />
  return istAngemeldet ? children : <Navigate to="/login" replace />
}

/** Nur für Admins — zeigt Ladeindikator bis Auth geklärt, leitet sonst zur Startseite */
function AdminRoute({ children }) {
  const { isAdmin, loadingAuth, hasModule } = useAuth()
  if (loadingAuth) return <AuthSpinner />
  return isAdmin ? children : <Navigate to={homeRoute(hasModule)} replace />
}

/** Nur mit freigeschaltetem Modul — leitet sonst zur Startseite des Benutzers */
function ModuleRoute({ module, children }) {
  const { loadingAuth, hasModule } = useAuth()
  if (loadingAuth) return <AuthSpinner />
  return hasModule(module) ? children : <Navigate to={homeRoute(hasModule)} replace />
}

/** Startseite: Dashboard, sonst erstes freigeschaltetes Modul */
function HomeRedirect() {
  const { loadingAuth, hasModule } = useAuth()
  if (loadingAuth) return <AuthSpinner />
  return <Navigate to={homeRoute(hasModule)} replace />
}

function App() {
  return (
    <BrowserRouter>
      <SettingsProvider>
        <AuthProvider>
          {/* Safe-Area-Abstand: am iPhone erscheinen Toasts sonst unter Notch/Kamera */}
          <Toaster position="top-right" toastOptions={{ duration: 4000 }}
            containerStyle={{ top: 'calc(env(safe-area-inset-top, 0px) + 16px)' }} />
          <Routes>
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            {/* Ziel des Links aus der E-Mail. Der Pfad steht auch im Backend
                (api/auth.py, password_forgot) — beide müssen zusammenpassen. */}
            <Route path="/passwort-neu" element={<ResetPasswordPage />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Routes>
                      <Route path="/dashboard"            element={<ModuleRoute module="dashboard"><DashboardPage /></ModuleRoute>} />
                      <Route path="/masterdata"           element={<ModuleRoute module="stammdaten"><MasterDataOverview /></ModuleRoute>} />
                      <Route path="/masterdata/:slug"     element={<ModuleRoute module="stammdaten"><MasterDataDetail /></ModuleRoute>} />
                      <Route path="/profile"              element={<ProfilePage />} />
                      <Route path="/users"                element={<UserManagementPage />} />
                      <Route path="/zeiterfassung"        element={<ModuleRoute module="zeiterfassung"><ZeiterfassungPage /></ModuleRoute>} />
                      <Route path="/aufgaben"             element={<ModuleRoute module="aufgaben"><AufgabenPage /></ModuleRoute>} />
                      <Route path="/postecke"             element={<ModuleRoute module="postecke"><PosteckePage /></ModuleRoute>} />
                      <Route path="/projekte"             element={<ModuleRoute module="projekte"><ProjektplanPage /></ModuleRoute>} />
                      <Route path="/projekte/einstellungen" element={<AdminRoute><ProjekteEinstellungen /></AdminRoute>} />
                      <Route path="/projekte/:id"         element={<ModuleRoute module="projekte"><ProjektplanDetailPage /></ModuleRoute>} />
                      <Route path="/datacenter"           element={<ModuleRoute module="datacenter"><DatacenterPage /></ModuleRoute>} />
                      {/* Rechnungsmodul */}
                      <Route path="/invoices"            element={<ModuleRoute module="verkauf"><InvoicePage /></ModuleRoute>} />
                      <Route path="/invoices/new"        element={<ModuleRoute module="verkauf"><InvoiceFormPage /></ModuleRoute>} />
                      {/* Die Auswertungen sind in den Bereich Buchhaltung
                          gezogen. Die alten Pfade bleiben als Weiterleitung
                          bestehen — sie stecken in Lesezeichen und in
                          PWA-Verknüpfungen auf dem Startbildschirm. */}
                      <Route path="/invoices/book"       element={<Navigate to="/buchhaltung/verkaufsbuch" replace />} />
                      <Route path="/invoices/open-items" element={<Navigate to="/buchhaltung/offene-posten" replace />} />
                      <Route path="/invoices/abschluss"  element={<Navigate to="/buchhaltung/abschluss" replace />} />
                      <Route path="/invoices/mahnlauf"   element={<Navigate to="/buchhaltung/mahnlauf" replace />} />

                      {/* Bereich Buchhaltung */}
                      <Route path="/buchhaltung"                element={<ModuleRoute module="buchhaltung"><BuchhaltungPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/offene-posten"   element={<ModuleRoute module="buchhaltung"><OpenItemsPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/mahnlauf"        element={<ModuleRoute module="buchhaltung"><MahnlaufPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/auswertungen"   element={<ModuleRoute module="buchhaltung"><AuswertungenPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/verkaufsbuch"    element={<ModuleRoute module="buchhaltung"><InvoiceBookPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/abschluss"       element={<ModuleRoute module="buchhaltung"><MonatsabschlussPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/konten"          element={<ModuleRoute module="buchhaltung"><KontenplanPage /></ModuleRoute>} />
                      <Route path="/buchhaltung/eingangsrechnungen" element={<ModuleRoute module="buchhaltung"><EingangsrechnungenPage /></ModuleRoute>} />
                      <Route path="/invoices/:id"        element={<ModuleRoute module="verkauf"><InvoiceFormPage /></ModuleRoute>} />
                      <Route path="/invoices/:id/edit"   element={<ModuleRoute module="verkauf"><InvoiceFormPage /></ModuleRoute>} />
                      {/* Feldverwaltung & Einstellungen: nur Admin */}
                      <Route path="/zeiterfassung/felder" element={<AdminRoute><ZeiterfassungFelder /></AdminRoute>} />
                      <Route path="/settings"             element={<AdminRoute><SettingsPage /></AdminRoute>} />
                      <Route path="*"                     element={<HomeRedirect />} />
                    </Routes>
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            {/* Hinweis: /dashboard leitet über ModuleRoute ggf. weiter zur
                Startseite des Benutzers (erstes freigeschaltetes Modul) */}
          </Routes>
        </AuthProvider>
      </SettingsProvider>
    </BrowserRouter>
  )
}

// Anzeige-Präferenzen (Dunkelmodus, Barrierefreiheit) vor dem ersten Render anwenden
initPrefs()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
