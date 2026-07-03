import React, { Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { Loader2 } from 'lucide-react'
import './i18n'
import './index.css'

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
import Layout from './components/Layout'

function ProtectedRoute({ children }) {
  const token = localStorage.getItem('access_token')
  return token ? children : <Navigate to="/login" replace />
}

/** Nur für Admins — zeigt Ladeindikator bis Auth geklärt, leitet sonst zum Dashboard */
function AdminRoute({ children }) {
  const { isAdmin, loadingAuth } = useAuth()
  if (loadingAuth) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={28} className="animate-spin text-primary-400" />
    </div>
  )
  return isAdmin ? children : <Navigate to="/dashboard" replace />
}

function App() {
  return (
    <BrowserRouter>
      <SettingsProvider>
        <AuthProvider>
          <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Routes>
                      <Route path="/dashboard"            element={<DashboardPage />} />
                      <Route path="/masterdata"           element={<MasterDataOverview />} />
                      <Route path="/masterdata/:slug"     element={<MasterDataDetail />} />
                      <Route path="/profile"              element={<ProfilePage />} />
                      <Route path="/users"                element={<UserManagementPage />} />
                      <Route path="/zeiterfassung"        element={<ZeiterfassungPage />} />
                      <Route path="/aufgaben"             element={<AufgabenPage />} />
                      <Route path="/projekte"             element={<ProjektplanPage />} />
                      <Route path="/projekte/einstellungen" element={<AdminRoute><ProjekteEinstellungen /></AdminRoute>} />
                      <Route path="/projekte/:id"         element={<ProjektplanDetailPage />} />
                      <Route path="/datacenter"           element={<DatacenterPage />} />
                      {/* Rechnungsmodul */}
                      <Route path="/invoices"            element={<InvoicePage />} />
                      <Route path="/invoices/new"        element={<InvoiceFormPage />} />
                      <Route path="/invoices/book"       element={<InvoiceBookPage />} />
                      <Route path="/invoices/:id"        element={<InvoiceFormPage />} />
                      <Route path="/invoices/:id/edit"   element={<InvoiceFormPage />} />
                      {/* Feldverwaltung & Einstellungen: nur Admin */}
                      <Route path="/zeiterfassung/felder" element={<AdminRoute><ZeiterfassungFelder /></AdminRoute>} />
                      <Route path="/settings"             element={<AdminRoute><SettingsPage /></AdminRoute>} />
                      <Route path="*"                     element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </SettingsProvider>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
