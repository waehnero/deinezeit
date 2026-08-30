import axios from 'axios'

/* ════════════════════════════════════════════════════════════════════════════
 * Token-Verwaltung
 * ════════════════════════════════════════════════════════════════════════════
 * Der Access-Token liegt seit der Sicherheits-Etappe nur noch im Arbeits-
 * speicher dieses Moduls, nicht mehr in localStorage. Der langlebige
 * Refresh-Token steckt in einem httpOnly-Cookie und ist für JavaScript
 * grundsätzlich unerreichbar.
 *
 * Der Grund: In localStorage abgelegte Token kann jedes Skript lesen, das im
 * Seitenkontext läuft. Eine einzige XSS-Lücke — auch in einer eingebundenen
 * Fremdbibliothek — reichte damit aus, um eine sieben Tage gültige Sitzung
 * mitzunehmen. Im Arbeitsspeicher ist der Token beim Neuladen der Seite weg
 * und lebt ohnehin nur 30 Minuten.
 *
 * Dass die Anmeldung ein Neuladen übersteht, erledigt der Cookie: Beim Start
 * holt die Anwendung über /auth/refresh einen frischen Access-Token
 * (siehe sitzungWiederherstellen).
 */

let accessToken = null

/** Merker, ob eine Anmeldung bestand — steuert nur die Oberfläche beim Start.
 *  Enthält absichtlich kein Geheimnis, sondern nur „ja/nein". */
const ANGEMELDET_FLAG = 'dz_angemeldet'

export function setAccessToken(token) {
  accessToken = token || null
  if (token) localStorage.setItem(ANGEMELDET_FLAG, '1')
}

export function getAccessToken() {
  return accessToken
}

export function warAngemeldet() {
  return localStorage.getItem(ANGEMELDET_FLAG) === '1'
}

/** Lokalen Anmeldezustand verwerfen (ohne Server-Aufruf). */
export function tokenVerwerfen() {
  accessToken = null
  localStorage.removeItem(ANGEMELDET_FLAG)
  // Aufräumen: Bis zu dieser Etappe lagen hier echte Token. Auf Geräten, die
  // schon länger im Einsatz sind, sollen sie nicht liegen bleiben.
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  // Damit der httpOnly-Cookie mitgeschickt wird, auch wenn Oberfläche und API
  // unter verschiedenen Namen erreichbar sind.
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

/* ── Stiller Refresh ─────────────────────────────────────────────────────────
 * Vorher warf der Interceptor bei jedem 401 sofort zur Anmeldeseite. Weil der
 * Access-Token nach 30 Minuten abläuft und der Refresh-Token nie benutzt
 * wurde, bedeutete das: mitten in der Arbeit, ohne Vorwarnung, ungespeicherte
 * Eingaben verloren. Jetzt wird die Sitzung im Hintergrund erneuert und die
 * fehlgeschlagene Anfrage wiederholt. Erst wenn auch das nicht klappt, ist
 * die Sitzung wirklich zu Ende.
 */

let refreshLaeuft = null
let abmeldeHandler = null

/** Wird von der Anwendung gesetzt, damit dieses Modul die Oberfläche nicht
 *  selbst per window.location umleiten muss. */
export function setAbmeldeHandler(fn) {
  abmeldeHandler = fn
}

async function tokenErneuern() {
  // Mehrere gleichzeitig fehlschlagende Anfragen dürfen nur EINEN
  // Erneuerungsvorgang auslösen. Sonst löst jede parallele Anfrage eine eigene
  // Rotation aus, und weil dabei jeder Refresh-Token nur einmal gilt, würden
  // die späteren als „bereits verbraucht" gewertet — der Server entwertet dann
  // die ganze Sitzungskette und wirft den Benutzer hinaus.
  if (!refreshLaeuft) {
    refreshLaeuft = axios
      .post('/api/auth/refresh', null, { withCredentials: true })
      .then((r) => {
        setAccessToken(r.data.access_token)
        return r.data.access_token
      })
      .finally(() => { refreshLaeuft = null })
  }
  return refreshLaeuft
}

/** Beim Start der Anwendung: Sitzung aus dem Cookie wiederherstellen. */
export async function sitzungWiederherstellen() {
  try {
    return await tokenErneuern()
  } catch {
    tokenVerwerfen()
    return null
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config || {}
    const istAnmeldeAufruf = (config.url || '').includes('/auth/refresh')
      || (config.url || '').includes('/auth/login')

    if (error.response?.status === 401 && !config._erneuert && !istAnmeldeAufruf) {
      config._erneuert = true
      try {
        const neuerToken = await tokenErneuern()
        config.headers = { ...config.headers, Authorization: `Bearer ${neuerToken}` }
        return api.request(config)
      } catch {
        tokenVerwerfen()
        if (abmeldeHandler) abmeldeHandler()
        else window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

export const authApi = {
  login: (email, password, totpCode, recoveryCode) =>
    api.post('/auth/login', {
      email, password, totp_code: totpCode, recovery_code: recoveryCode,
    }),
  me: () => api.get('/auth/me'),

  // ── Sitzungen ─────────────────────────────────────────────────────────────
  refresh:   () => api.post('/auth/refresh'),
  logout:    () => api.post('/auth/logout'),
  logoutAll: () => api.post('/auth/logout-all'),
  sessions:  () => api.get('/auth/sessions'),
  revokeSession: (id) => api.delete(`/auth/sessions/${id}`),
  events:    (limit = 30) => api.get('/auth/events', { params: { limit } }),

  // ── Passwort ──────────────────────────────────────────────────────────────
  forgotPassword: (email) => api.post('/auth/password/forgot', { email }),
  resetPassword:  (token, newPassword) =>
    api.post('/auth/password/reset', { token, new_password: newPassword }),
  changePassword: (currentPassword, newPassword) =>
    api.post('/auth/password/change', {
      current_password: currentPassword, new_password: newPassword,
    }),

  // ── 2FA ───────────────────────────────────────────────────────────────────
  setupTotp: () => api.post('/auth/totp/setup'),
  // Das Secret wird NICHT mehr mitgeschickt — der Server hat es vorgemerkt.
  // Vorher hing es als Query-Parameter in der URL und landete damit in
  // Zugriffslogs und im Browserverlauf.
  enableTotp: (code) => api.post('/auth/totp/enable', { code }),
  disableTotp: (code) => api.post('/auth/totp/disable', { code }),
  recoveryCodesNeu:    (code) => api.post('/auth/recovery-codes', { code }),
  recoveryCodesStatus: () => api.get('/auth/recovery-codes/status'),

  // ── Passkeys ──────────────────────────────────────────────────────────────
  webauthnRegisterBegin:    () => api.post('/auth/webauthn/register/begin'),
  webauthnRegisterComplete: (credential, deviceName) =>
    api.post('/auth/webauthn/register/complete', { credential, device_name: deviceName }),
  // E-Mail im Anfragetext statt im Query-String (URLs landen in Logs).
  webauthnLoginBegin:       (email) => api.post('/auth/webauthn/login/begin', { email }),
  webauthnLoginComplete:    (email, credential) =>
    api.post('/auth/webauthn/login/complete', { email, credential }),
}

// ── Erstinstallations-Assistent ──────────────────────────────────────────────
export const setupApi = {
  status: () => api.get('/setup/status'),
  init:   (data) => api.post('/setup/init', data),
}

export const usersApi = {
  list: () => api.get('/users/'),
  create: (data) => api.post('/users/', data),
  updateMe: (data) => api.put('/users/me', data),
  updateByAdmin: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
  // Kontosperre nach Fehlversuchen vorzeitig aufheben (nur Admin).
  unlock: (id) => api.post(`/users/${id}/unlock`),
  // Persönliche Dashboard-Konfiguration (serverseitig, je Benutzer)
  getDashboard: () => api.get('/users/me/dashboard'),
  saveDashboard: (config) => api.put('/users/me/dashboard', { config }),
}

// ── Rechtegruppen (Migration 0055) ───────────────────────────────────────────
export const groupsApi = {
  // Beschreibung des Rechtemodells: Module, vergebbare Rechte, Umfänge.
  // Kommt vom Server, damit die Rechtematrix nicht dieselbe Liste doppelt
  // pflegt — die liefe sonst auseinander, sobald ein Modul dazukommt.
  katalog: () => api.get('/groups/katalog'),

  list:   () => api.get('/groups/'),
  create: (data) => api.post('/groups/', data),
  update: (id, data) => api.put(`/groups/${id}`, data),
  delete: (id) => api.delete(`/groups/${id}`),

  // Gruppenzugehörigkeit eines Benutzers ersetzen
  setUserGroups: (userId, groupIds) =>
    api.put(`/groups/users/${userId}/groups`, { group_ids: groupIds }),
  // Individuelle Abweichungen (null löscht alle)
  setOverrides: (userId, overrides) =>
    api.put(`/groups/users/${userId}/overrides`, { overrides }),

  // Effektive Rechte samt Herkunft — ohne diese Auskunft wird die
  // Rechteverwaltung zur Ratesache.
  userRechte: (userId) => api.get(`/groups/users/${userId}/rechte`),
  meineRechte: () => api.get('/groups/me/rechte'),
}

export const dashboardApi = {
  // Sammelt die Kennzahlen aller sichtbaren Kacheln in einem Aufruf.
  // `bausteine` ist ein Array von Widget-Typen; leer/weggelassen = alle
  // Bausteine, die der Benutzer sehen darf.
  kennzahlen: (bausteine) => api.get('/dashboard/kennzahlen', {
    params: bausteine?.length ? { bausteine: bausteine.join(',') } : {},
  }),
}

export const masterdataApi = {
  // Stammdaten-Typen
  listTypes: () => api.get('/masterdata/types'),
  getType: (slug) => api.get(`/masterdata/types/${slug}`),
  createType: (data) => api.post('/masterdata/types', data),
  updateType: (slug, data) => api.put(`/masterdata/types/${slug}`, data),
  deleteType: (slug) => api.delete(`/masterdata/types/${slug}`),

  // Felder
  addField: (slug, data) => api.post(`/masterdata/types/${slug}/fields`, data),
  updateField: (slug, fieldId, data) => api.put(`/masterdata/types/${slug}/fields/${fieldId}`, data),
  deleteField: (slug, fieldId) => api.delete(`/masterdata/types/${slug}/fields/${fieldId}`),
  updateFieldOrder: (slug, orders) => api.put(`/masterdata/types/${slug}/fields-order`, { orders }),
  updateFieldsLayout: (slug, layout) => api.put(`/masterdata/types/${slug}/fields-layout`, layout),
  updateTabs: (slug, tabs) => api.put(`/masterdata/types/${slug}/tabs`, { tabs }),

  // Datensätze
  listRecords: (slug, params) => api.get(`/masterdata/types/${slug}/records`, { params }),
  getRecord: (slug, id) => api.get(`/masterdata/types/${slug}/records/${id}`),
  createRecord: (slug, data) => api.post(`/masterdata/types/${slug}/records`, { data }),
  updateRecord: (slug, id, data) => api.put(`/masterdata/types/${slug}/records/${id}`, { data }),
  deleteRecord: (slug, id) => api.delete(`/masterdata/types/${slug}/records/${id}`),
  getRecordReferences: (slug, id) => api.get(`/masterdata/types/${slug}/records/${id}/references`),
  archiveRecord: (slug, id) => api.post(`/masterdata/types/${slug}/records/${id}/archive`),
  restoreRecord: (slug, id) => api.post(`/masterdata/types/${slug}/records/${id}/restore`),
  exportCsv: (slug) => api.get(`/masterdata/types/${slug}/records/export/csv`, { responseType: 'text' }),
  // Import: derselbe Aufruf für Probelauf und echten Lauf. `optionen` =
  // { match_field, dry_run, skip_invalid }; ohne Angabe ist es ein Probelauf.
  importRecords: (slug, rows, optionen = {}) =>
    api.post(`/masterdata/types/${slug}/records/import`, { rows, ...optionen }),

  // Artikelgruppen — eigene Tabelle, siehe Modell ArticleGroup
  listArticleGroups:  (params) => api.get('/masterdata/artikelgruppen', { params }),
  createArticleGroup: (data) => api.post('/masterdata/artikelgruppen', data),
  updateArticleGroup: (id, data) => api.put(`/masterdata/artikelgruppen/${id}`, data),
  deleteArticleGroup: (id) => api.delete(`/masterdata/artikelgruppen/${id}`),

  // Artikel: Nummernvorschlag (verbraucht den Zähler NICHT) und aufgelöste
  // Vorgabewerte für die Belegposition
  naechsteArtikelnummer: (gruppe) =>
    api.get('/masterdata/artikel/naechste-nummer', { params: { gruppe } }),
  artikelVorgaben: (recordId) => api.get(`/masterdata/artikel/${recordId}/vorgaben`),

  // Bilder an Stammdatensätzen (Feldtyp „image")
  uploadBild: (datei, size = 'mittel') => {
    const form = new FormData()
    form.append('file', datei)
    return api.post('/masterdata/bild', form, {
      params: { size },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  bildUrl: (key, provider) =>
    `/api/masterdata/bild?key=${encodeURIComponent(key)}` +
    (provider ? `&provider=${encodeURIComponent(provider)}` : ''),
}

export const zeiterfassungApi = {
  // Abrechnungs-Status
  setEntryStatus: (id, status) => api.put(`/zeiterfassung/entries/${id}/status`, { status }),
  setEntriesStatusBatch: (entryIds, status) =>
    api.post('/zeiterfassung/entries/status-batch', { entry_ids: entryIds, status }),

  // Custom-Felder
  listFields: () => api.get('/zeiterfassung/fields'),
  createField: (data) => api.post('/zeiterfassung/fields', data),
  updateField: (id, data) => api.put(`/zeiterfassung/fields/${id}`, data),
  deleteField: (id) => api.delete(`/zeiterfassung/fields/${id}`),
  updateFieldOrder: (updates) => api.post('/zeiterfassung/fields/sort-orders', { updates }),

  // Timer
  getRunning: () => api.get('/zeiterfassung/running'),
  startTimer: (data) => api.post('/zeiterfassung/start', data),
  stopTimer: (id, data) => api.post(`/zeiterfassung/${id}/stop`, data),

  // Einträge
  listEntries: (params) => api.get('/zeiterfassung/entries', { params }),
  createEntry: (data) => api.post('/zeiterfassung/entries', data),
  updateEntry: (id, data) => api.put(`/zeiterfassung/entries/${id}`, data),
  deleteEntry: (id) => api.delete(`/zeiterfassung/entries/${id}`),

  // Statistik
  getStats: (userId) => api.get('/zeiterfassung/stats', { params: userId ? { user_id: userId } : {} }),

  // KI: Sprach-Nachtragen (Transkript auswerten → Vorschlag)
  kiNachtragen: (transcript) => api.post('/zeiterfassung/ki-nachtragen', { transcript }),

  // Stundenkonten / Projekt-Budgets
  listStundenkonten: (projectId) => api.get(`/zeiterfassung/projekte/${projectId}/stundenkonten`),
  createStundenkonto: (projectId, data) => api.post(`/zeiterfassung/projekte/${projectId}/stundenkonten`, data),
  updateStundenkonto: (id, data) => api.put(`/zeiterfassung/stundenkonten/${id}`, data),
  deleteStundenkonto: (id) => api.delete(`/zeiterfassung/stundenkonten/${id}`),
  getBudgets: (projectIds) => api.get('/zeiterfassung/budgets', { params: { project_ids: projectIds.join(',') } }),
}

export const reportsApi = {
  downloadZeiterfassung: (params) =>
    api.get('/reports/zeiterfassung', { params, responseType: 'blob' }),
  previewZeiterfassung: (params) =>
    api.get('/reports/zeiterfassung', { params: { ...params, format: 'html' }, responseType: 'text' }),
  getContacts: () => api.get('/reports/zeiterfassung/contacts'),
  getTasks:    () => api.get('/reports/zeiterfassung/tasks'),
}

export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
  uploadLogo: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/settings/logo', form, { headers: { 'Content-Type': undefined } })
  },
  deleteLogo: () => api.delete('/settings/logo'),
  uploadFavicon: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/settings/favicon', form, { headers: { 'Content-Type': undefined } })
  },
  getCompanyContact: () => api.get('/settings/company-contact'),
  getContactOptions: () => api.get('/settings/contact-options'),
  testEmail: (toEmail) => api.post('/settings/test-email', { to_email: toEmail }),
  downloadBackup: () => api.get('/settings/backup/download', { responseType: 'blob' }),
  testBackupOnedrive: (data) => api.post('/settings/backup/onedrive/test', data),
  runBackup:      ()     => api.post('/settings/backup/run'),
  testStorage:    (data) => api.post('/settings/storage/test', data),
  applyStorage:   ()     => api.post('/settings/storage/apply'),
  storageMigrationStatus: () => api.get('/settings/storage/migration-status'),
  // Migration kann je nach Dateimenge dauern → großzügiges Timeout
  storageMigrate: (deleteSource) => api.post('/settings/storage/migrate',
    { delete_source: !!deleteSource }, { timeout: 600000 }),
  storageRepathStatus: () => api.get('/settings/storage/repath-status'),
  storageRepath: () => api.post('/settings/storage/repath', {}, { timeout: 600000 }),
}

export const datacenterApi = {
  // Dashboard-Widget: Gesamtanzahl, Neuzugänge, neueste Dateien
  stats:           (limit = 3) => api.get('/datacenter/stats', { params: { limit } }),
  // Alle Anhänge laden (optional gefiltert nach entityType und/oder entityId)
  listAll:         (entityType, entityId, contactId) => {
    const params = {}
    if (entityType) params.entity_type = entityType
    if (entityId)   params.entity_id   = entityId
    if (contactId !== undefined && contactId !== null) params.contact_id = contactId
    return api.get('/datacenter/all', { params })
  },
  updateContact:   (attachmentId, contactId, contactName) =>
    api.patch(`/datacenter/${attachmentId}/contact`, { contact_id: contactId, contact_name: contactName }),
  // Anhänge für einen konkreten Datensatz laden
  list:            (entityType, entityId) => api.get(`/datacenter/${entityType}/${entityId}`),
  upload:          (entityType, entityId, file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    // WICHTIG: Content-Type NICHT fest auf 'multipart/form-data' setzen.
    // Dann fehlt die boundary und der Server kann den Body nicht parsen.
    // Mit null/undefined ergänzt der Browser den korrekten Header inkl. boundary.
    return api.post(`/datacenter/${entityType}/${entityId}/upload`, form, {
      headers: { 'Content-Type': undefined },
      onUploadProgress: onProgress,
    })
  },
  addLink:         (data) => api.post('/datacenter/link', data),
  download:        (id) => api.get(`/datacenter/${id}/download`, { responseType: 'blob' }),
  preview:         (id) => api.get(`/datacenter/${id}/preview`, { responseType: 'blob' }),
  previewRaw:      (id, responseType) => api.get(`/datacenter/${id}/preview`, { responseType }),
  download_blob:   (id) => api.get(`/datacenter/${id}/download`, { responseType: 'blob' }),
  createShareLink: (id, expiresHours) => api.post(`/datacenter/${id}/share-link`, { expires_hours: expiresHours }),
  extendShareLink: (id, expiresHours) => api.patch(`/datacenter/${id}/share-link`, { expires_hours: expiresHours }),
  deleteShareLink: (id) => api.delete(`/datacenter/${id}/share-link`),
  delete:          (id) => api.delete(`/datacenter/${id}`),
  getProviders:    () => api.get('/datacenter/providers'),
}

export const systemApi = {
  getVersion:      () => api.get('/system/version'),
  getChangelog:    () => api.get('/system/changelog'),
  getActiveUsers:  () => api.get('/system/active-users'),
  getSslStatus:    () => api.get('/system/ssl-status'),
  getUpdateStatus: () => api.get('/system/update-status'),
  startUpdate:     () => api.post('/system/update/start'),
  cancelUpdate:    () => api.post('/system/update/cancel'),

  // Angemeldete Sitzungen (nur Administrator). Grundlage ist user_sessions,
  // nicht die Zählung im Arbeitsspeicher — die stimmt mit mehreren
  // Arbeitsprozessen nicht mehr.
  listSitzungen:      () => api.get('/system/sitzungen'),
  beendeSitzung:      (id) => api.delete(`/system/sitzungen/${id}`),
  beendeBenutzer:     (userId) => api.delete(`/system/sitzungen/benutzer/${userId}`),
}

export const invoiceApi = {
  // Liste & Detail
  list:           (params) => api.get('/invoices', { params }),
  get:            (id) => api.get(`/invoices/${id}`),
  create:         (data) => api.post('/invoices', data),
  update:         (id, data) => api.put(`/invoices/${id}`, data),
  delete:         (id) => api.delete(`/invoices/${id}`),

  // Nächste Nummer vorschau
  nextNumber:     (doc_type, year) => api.get('/invoices/next-number', { params: { doc_type, year } }),

  // Aktionen
  setStatus:        (id, status) => api.post(`/invoices/${id}/set-status`, { status }),
  // trotzAblauf: abgelaufenes Angebot dennoch umwandeln (nach Rückfrage)
  convertToAb:      (id, trotzAblauf = false) =>
    api.post(`/invoices/${id}/convert-to-ab`, null, { params: { trotz_ablauf: trotzAblauf } }),
  cancel:           (id, cancel_mode) => api.post(`/invoices/${id}/cancel`, { cancel_mode }),
  sendEmail:        (id, to_email, extra_attachments = [], cc_email = '', subject = '', body_html = '') => api.post(`/invoices/${id}/send-email`, { to_email, extra_attachments, cc_email, subject, body_html }),
  bulkSendEmail:    (invoice_ids) => api.post('/invoices/bulk-send-email', { invoice_ids }),
  markPaid:       (id, data) => api.post(`/invoices/${id}/mark-paid`, data),
  convertToInvoice: (id, trotzAblauf = false) =>
    api.post(`/invoices/${id}/convert-to-invoice`, null, { params: { trotz_ablauf: trotzAblauf } }),
  duplicate:        (id, opts) => api.post(`/invoices/${id}/duplicate`, opts || {}),

  // Abrechnung in Stufen (Anzahlung → Teil → Schluss)
  chain:            (id) => api.get(`/invoices/${id}/chain`),
  // Anzahlung aus Angebot/AB: entweder percent ODER amount
  createAdvance:    (id, data, trotzAblauf = false) =>
    api.post(`/invoices/${id}/anzahlung`, data, { params: { trotz_ablauf: trotzAblauf } }),
  createFinal:      (id, data) => api.post(`/invoices/${id}/schlussrechnung`, data || {}),

  // E-Rechnung (ZUGFeRD 2.5 / Factur-X)
  // Auswertungen (C-15) — Stichtag ist das Belegdatum, wie in UVA und Verkaufsbuch
  umsatzJahr:     (jahr) => api.get('/invoices/auswertung/umsatz-jahr', { params: { jahr } }),
  umsatzKunden:   (params) => api.get('/invoices/auswertung/umsatz-kunden', { params }),
  umsatzArtikel:  (params) => api.get('/invoices/auswertung/umsatz-artikel', { params }),
  angebotsquote:  (params) => api.get('/invoices/auswertung/angebotsquote', { params }),

  erechnungPruefen: (id) => api.get(`/invoices/${id}/erechnung/pruefen`),
  erechnungXmlUrl:  (id, trotzLuecken = false) =>
    `/api/invoices/${id}/erechnung/xml` + (trotzLuecken ? '?trotz_luecken=true' : ''),
  uploadContract:   (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/invoices/${id}/contract`, form, { headers: { 'Content-Type': undefined } })
  },
  deleteContract:   (attachmentId) => api.delete(`/invoices/contract/${attachmentId}`),

  // Zeiteinträge
  unbilledEntries: (params) => api.get('/invoices/time-entries/unbilled', { params }),

  // Änderungsprotokoll
  getAudit:       (id) => api.get(`/invoices/${id}/audit`),

  // Positionsbilder
  uploadPositionImage: (file, size) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/invoices/positions/image?size=${size}`, form,
                    { headers: { 'Content-Type': undefined } })
  },
  // provider: Speicher der Datei. Im Mischbetrieb liegt ein älteres Bild noch
  // im alten Speicher — ohne diese Angabe wird am falschen Ort gesucht.
  positionImageUrl: (key, provider) =>
    `/api/invoices/positions/image?key=${encodeURIComponent(key)}`
    + (provider ? `&provider=${encodeURIComponent(provider)}` : ''),

  // Zahlungen & offene Posten
  listPayments:   (id) => api.get(`/invoices/${id}/payments`),
  addPayment:     (id, data) => api.post(`/invoices/${id}/payments`, data),
  deletePayment:  (paymentId) => api.delete(`/invoices/payments/${paymentId}`),
  openItems:      (params) => api.get('/invoices/open-items', { params }),
  uva:            (params) => api.get('/invoices/uva', { params }),
  uvaPdf:         (params) => api.get('/invoices/uva/pdf', { params, responseType: 'blob' }),

  // Mahnwesen
  dunningRun:     (params) => api.get('/invoices/dunning/run', { params }),
  dunningBatch:   (data) => api.post('/invoices/dunning/batch', data),
  dunningHistory: (id) => api.get(`/invoices/${id}/dunning`),
  createDunning:  (id, data) => api.post(`/invoices/${id}/dunning`, data),
  deleteDunning:  (dunningId) => api.delete(`/invoices/dunning/${dunningId}`),
  dunningBlock:   (id, data) => api.post(`/invoices/${id}/dunning-block`, data),
  dunningPdf:     (dunningId) => api.get(`/invoices/dunning/${dunningId}/pdf`,
                                         { responseType: 'blob' }),

  // Skonto
  skontoPreview:  (id, paid_at) => api.get(`/invoices/${id}/skonto`, { params: { paid_at } }),
  grantSkonto:    (id, data) => api.post(`/invoices/${id}/skonto`, data),

  // Rechnungsbuch
  book:           (params) => api.get('/invoices/book/list', { params }),
  // (Eingangsrechnungen siehe purchaseApi weiter unten)
  bookCsv:        (params) => api.get('/invoices/book/csv', { params, responseType: 'blob' }),

  // E-Mail-Vorlagen
  getEmailTemplate:    (doc_type) => api.get(`/invoices/email-templates/${doc_type}`),
  updateEmailTemplate: (doc_type, data) => api.put(`/invoices/email-templates/${doc_type}`, data),

  // Einstellungen
  getSettings:    () => api.get('/invoices/settings/all'),
  updateSetting:  (key, value) => api.put(`/invoices/settings/${key}`, { key, value }),

  // Wiederkehrende Vorlagen
  listTemplates:  () => api.get('/invoices/templates'),

  // PDF
  downloadPdf:        (id) => api.get(`/invoices/${id}/pdf`, { responseType: 'blob' }),
  bookPdf:            (params) => api.get('/invoices/book/pdf', { params, responseType: 'blob' }),

  // Belegnummern
  getNumberSequences: (year) => api.get('/invoices/number-sequences', { params: year ? { year } : {} }),
  updateNumberSequence: (docType, data) => api.put(`/invoices/number-sequences/${docType}`, data),
}

export const periodApi = {
  list:       (jahr) => api.get('/periods', { params: jahr ? { jahr } : {} }),
  check:      (jahr, monat) => api.get(`/periods/${jahr}/${monat}/check`),
  close:      (jahr, monat) => api.post(`/periods/${jahr}/${monat}/close`),
  reopen:     (jahr, monat, grund) => api.post(`/periods/${jahr}/${monat}/reopen`, { grund }),
  package:    (jahr, monat) => api.get(`/periods/${jahr}/${monat}/package`, { responseType: 'blob' }),
  handovers:  (jahr, monat) => api.get(`/periods/${jahr}/${monat}/handovers`),
}

export const accountingApi = {
  listAccounts:       (params) => api.get('/accounting/accounts', { params }),
  createAccount:      (data)   => api.post('/accounting/accounts', data),
  updateAccount:      (id, data) => api.put(`/accounting/accounts/${id}`, data),
  deleteAccount:      (id)     => api.delete(`/accounting/accounts/${id}`),
  setDefaultErloes:   (id)     => api.post(`/accounting/accounts/${id}/set-default-erloes`),
  exportBmd:          (params) => api.get('/accounting/export/bmd', { params, responseType: 'blob' }),
  exportBmdEingang:   (params) => api.get('/accounting/export/bmd-eingang', { params, responseType: 'blob' }),
}

// ── Eingangsrechnungen (Kreditoren) ──────────────────────────────────────────
export const purchaseApi = {
  list:        (params) => api.get('/purchase-invoices', { params }),
  get:         (id) => api.get(`/purchase-invoices/${id}`),
  create:      (data) => api.post('/purchase-invoices', data),
  update:      (id, data) => api.put(`/purchase-invoices/${id}`, data),
  cancel:      (id) => api.post(`/purchase-invoices/${id}/cancel`),
  remove:      (id) => api.delete(`/purchase-invoices/${id}`),

  listPayments: (id) => api.get(`/purchase-invoices/${id}/payments`),
  addPayment:   (id, data) => api.post(`/purchase-invoices/${id}/payments`, data),
  deletePayment: (paymentId) => api.delete(`/purchase-invoices/payments/${paymentId}`),

  openItems:   (params) => api.get('/purchase-invoices/open-items', { params }),
  vorsteuer:   (params) => api.get('/purchase-invoices/vorsteuer', { params }),

  uploadFile:  (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/purchase-invoices/${id}/file`, form,
                    { headers: { 'Content-Type': undefined } })
  },
  fileUrl:     (id) => `/api/purchase-invoices/${id}/file`,
}

// ── Projekt-Aufzeichnungstool (Projektplanung) ───────────────────────────────
export const projektplanApi = {
  // Projekte
  listProjects:   (params) => api.get('/projektplan/projects', { params }),
  recentProjects: (limit = 5) => api.get('/projektplan/projects/recent', { params: { limit } }),
  getProject:     (id)     => api.get(`/projektplan/projects/${id}`),
  createProject:  (data)   => api.post('/projektplan/projects', data),
  updateProject:  (id, data) => api.put(`/projektplan/projects/${id}`, data),
  deleteProject:  (id)     => api.delete(`/projektplan/projects/${id}`),
  duplicateProject: (id, opts) => api.post(`/projektplan/projects/${id}/duplicate`, opts || {}),

  // Aufgaben
  createTask:     (projectId, data) => api.post(`/projektplan/projects/${projectId}/tasks`, data),
  updateTask:     (taskId, data)    => api.put(`/projektplan/tasks/${taskId}`, data),
  deleteTask:     (taskId)          => api.delete(`/projektplan/tasks/${taskId}`),
  promoteTask:    (taskId, data)    => api.post(`/projektplan/tasks/${taskId}/promote`, data || {}),

  // Abhängigkeiten
  createDependency: (data)  => api.post('/projektplan/dependencies', data),
  deleteDependency: (id)    => api.delete(`/projektplan/dependencies/${id}`),

  // Gantt: Termine mehrerer Aufgaben aktualisieren (Drag)
  updateTaskDates: (updates) => api.put('/projektplan/tasks/dates', { updates }),

  // Meilensteine
  createMilestone: (projectId, data) => api.post(`/projektplan/projects/${projectId}/milestones`, data),
  updateMilestone: (id, data)        => api.put(`/projektplan/milestones/${id}`, data),
  deleteMilestone: (id)              => api.delete(`/projektplan/milestones/${id}`),

  // Konfigurierbare Aufgaben-Felder
  listFields:     ()         => api.get('/projektplan/fields'),
  createField:    (data)     => api.post('/projektplan/fields', data),
  updateField:    (id, data) => api.put(`/projektplan/fields/${id}`, data),
  deleteField:    (id)       => api.delete(`/projektplan/fields/${id}`),

  // Projekt-Einstellungen (Tags, Status, Prioritäten)
  getSettings:    ()     => api.get('/projektplan/settings'),
  updateSettings: (data) => api.put('/projektplan/settings', data),

  // Checklisten (parentType: 'project' | 'task')
  listChecklist:   (parentType, parentId) => api.get(`/projektplan/checklist/${parentType}/${parentId}`),
  addChecklist:    (parentType, parentId, data) => api.post(`/projektplan/checklist/${parentType}/${parentId}`, data),
  updateChecklist: (itemId, data) => api.put(`/projektplan/checklist/item/${itemId}`, data),
  deleteChecklist: (itemId) => api.delete(`/projektplan/checklist/item/${itemId}`),
  checklistToTask: (itemId) => api.post(`/projektplan/checklist/item/${itemId}/promote`),
  assignChecklist: (itemId, data) => api.post(`/projektplan/checklist/item/${itemId}/assign`, data),
}

// ── Aufgabenmodul (zentrale To-do-Liste) ─────────────────────────────────────
export const aufgabenApi = {
  list:   (params)     => api.get('/aufgaben/', { params }),
  get:    (id)         => api.get(`/aufgaben/${id}`),
  create: (data)       => api.post('/aufgaben/', data),
  update: (id, data)   => api.put(`/aufgaben/${id}`, data),
  remove: (id)         => api.delete(`/aufgaben/${id}`),
  printPdf: (id)       => api.get(`/aufgaben/${id}/print`, { responseType: 'blob' }),
  getSettings:    ()     => api.get('/aufgaben/einstellungen'),
  updateSettings: (data) => api.put('/aufgaben/einstellungen', data),
  // Dashboard-Widget: offene/fällige/überfällige Aufgaben + nächste Aufgaben
  stats: (params) => api.get('/aufgaben/stats', { params }),
}

// ── Mail-Import (Aufgabenmodul: KI-Vorschläge aus E-Mails) ───────────────────
export const mailImportApi = {
  listAccounts:  ()          => api.get('/mail-import/accounts'),
  createAccount: (data)      => api.post('/mail-import/accounts', data),
  updateAccount: (id, data)  => api.put(`/mail-import/accounts/${id}`, data),
  deleteAccount: (id)        => api.delete(`/mail-import/accounts/${id}`),
  listFolders:   (id)        => api.get(`/mail-import/accounts/${id}/folders`),
  scan:          (id)        => api.post(`/mail-import/accounts/${id}/scan`),
  listSuggestions: (status = 'offen') => api.get('/mail-import/suggestions', { params: { status } }),
  acceptSuggestion:  (id, data) => api.post(`/mail-import/suggestions/${id}/accept`, data || {}),
  dismissSuggestion: (id)       => api.post(`/mail-import/suggestions/${id}/dismiss`),
  getKiSettings:    ()     => api.get('/mail-import/ki-settings'),
  updateKiSettings: (data) => api.put('/mail-import/ki-settings', data),
}

// ── Postecke (Social-Media-Posts mit KI-Vorbereitung) ────────────────────────
export const posteckeApi = {
  // Profile (Social-Media-Konten inkl. Stil-Prompt)
  listProfile:   ()          => api.get('/postecke/profile'),
  createProfil:  (data)      => api.post('/postecke/profile', data),
  updateProfil:  (id, data)  => api.put(`/postecke/profile/${id}`, data),
  deleteProfil:  (id)        => api.delete(`/postecke/profile/${id}`),
  // Direktanbindung: hinterlegte Zugangsdaten gegen den Kanal prüfen
  testeVerbindung: (id)      => api.post(`/postecke/profile/${id}/verbindung-testen`),

  // Posts
  listPosts:  (status)     => api.get('/postecke/posts', { params: status ? { status } : {} }),
  getPost:    (id)         => api.get(`/postecke/posts/${id}`),
  createPost: (data)       => api.post('/postecke/posts', data),
  updatePost: (id, data)   => api.put(`/postecke/posts/${id}`, data),
  deletePost: (id)         => api.delete(`/postecke/posts/${id}`),
  setStatus:  (id, status, geplantAm) =>
    api.post(`/postecke/posts/${id}/status`, { status, geplant_am: geplantAm || null }),
  // Sofort über die Direktanbindung veröffentlichen (z.B. Facebook-Seite)
  veroeffentlichen: (id) => api.post(`/postecke/posts/${id}/veroeffentlichen`),

  // KI-Vorschlag (Fotos + Beschreibung + Profil-Stil)
  generieren: (id, beschreibung) =>
    api.post(`/postecke/posts/${id}/generieren`, { beschreibung: beschreibung || null }),

  // Fotos
  uploadFotos: (id, files) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    // Content-Type bewusst undefined: Browser setzt multipart-boundary selbst
    return api.post(`/postecke/posts/${id}/fotos`, form, { headers: { 'Content-Type': undefined } })
  },
  deleteFoto: (fotoId) => api.delete(`/postecke/fotos/${fotoId}`),
  // Foto als Blob laden (Bearer-Token nötig, daher kein direktes <img src>)
  getFoto:    (fotoId) => api.get(`/postecke/fotos/${fotoId}`, { responseType: 'blob' }),
  // Ausspielungs-Variante: Zielformat + Filter des Post-Profils angewendet (JPEG)
  getFotoAusspielung: (fotoId) =>
    api.get(`/postecke/fotos/${fotoId}/ausspielung`, { responseType: 'blob' }),

  // Video (max. eines je Post, MP4/MOV; kein Misch-Post mit Fotos)
  uploadVideo: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    // Content-Type bewusst undefined: Browser setzt multipart-boundary selbst
    return api.post(`/postecke/posts/${id}/video`, form, { headers: { 'Content-Type': undefined } })
  },
  deleteVideo: (videoId) => api.delete(`/postecke/videos/${videoId}`),
  // Video als Blob laden (Bearer-Token nötig, daher kein direktes <video src>)
  getVideo:    (videoId) => api.get(`/postecke/videos/${videoId}`, { responseType: 'blob' }),
  // Standbild (erstes Frame) des Videos als Blob — für die Vorschau
  getVideoPoster: (videoId) =>
    api.get(`/postecke/videos/${videoId}/poster`, { responseType: 'blob' }),
}

// ── Anlagen (Datacenter-API, generisch über entity_type/entity_id) ────────────
export const attachmentApi = {
  list:     (entityType, entityId) => api.get(`/datacenter/${entityType}/${entityId}`),
  upload:   (entityType, entityId, formData) =>
    // Content-Type bewusst auf undefined: Browser setzt multipart/form-data
    // inkl. boundary selbst. Fest gesetzt fehlt die boundary -> Server-Fehler.
    api.post(`/datacenter/${entityType}/${entityId}/upload`, formData, {
      headers: { 'Content-Type': undefined },
    }),
  remove:   (attachmentId) => api.delete(`/datacenter/${attachmentId}`),
  previewUrl:  (attachmentId) => `/api/datacenter/${attachmentId}/preview`,
  downloadUrl: (attachmentId) => `/api/datacenter/${attachmentId}/download`,
}

export default api
