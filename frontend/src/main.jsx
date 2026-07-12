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
import ForgotPasswordPage from './pages/ForgotPasswordPage'
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
import ProjektplanPage from './pages/ProjektplanPage'
import ProjektplanDetailPage from './pages/ProjektplanDetailPage'
import ProjekteEinstellungen from './pages/ProjekteEinstellungen'
import AufgabenPage from './pages/AufgabenPage'
import PosteckePage from './pages/PosteckePage'
import Layout, { homeRoute } from './components/Layout'

function ProtectedRoute({ children }) {
  const token = localStorage.getItem('access_token')
  return token ? children : <Navigate to="/login" replace />
}

const AuthSpinner = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 size={28} className="animate-spin text-primary-400" />
  </div>
)

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
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
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
                      <Route path="/invoices/book"       element={<ModuleRoute module="verkauf"><InvoiceBookPage /></ModuleRoute>} />
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
