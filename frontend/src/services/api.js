import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Token automatisch mitsenden
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Bei 401: automatisch ausloggen
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authApi = {
  login: (email, password, totpCode) =>
    api.post('/auth/login', { email, password, totp_code: totpCode }),
  me: () => api.get('/auth/me'),
  setupTotp: () => api.post('/auth/totp/setup'),
  enableTotp: (secret, code) => api.post(`/auth/totp/enable?secret=${secret}`, { code }),
  disableTotp: (code) => api.post('/auth/totp/disable', { code }),
  webauthnRegisterBegin:    () => api.post('/auth/webauthn/register/begin'),
  webauthnRegisterComplete: (credential, deviceName) =>
    api.post('/auth/webauthn/register/complete', { credential, device_name: deviceName }),
  webauthnLoginBegin:       (email) => api.post(`/auth/webauthn/login/begin?email=${email}`),
  webauthnLoginComplete:    (email, credential) =>
    api.post('/auth/webauthn/login/complete', { email, credential }),
}

export const usersApi = {
  list: () => api.get('/users/'),
  create: (data) => api.post('/users/', data),
  updateMe: (data) => api.put('/users/me', data),
  updateByAdmin: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
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
  exportCsv: (slug) => api.get(`/masterdata/types/${slug}/records/export/csv`, { responseType: 'text' }),
  importCsv: (slug, rows) => api.post(`/masterdata/types/${slug}/records/import/csv`, rows),
}

export const zeiterfassungApi = {
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
    return api.post('/settings/logo', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  deleteLogo: () => api.delete('/settings/logo'),
  uploadFavicon: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/settings/favicon', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  getCompanyContact: () => api.get('/settings/company-contact'),
  getContactOptions: () => api.get('/settings/contact-options'),
  testEmail: (toEmail) => api.post('/settings/test-email', { to_email: toEmail }),
  downloadBackup: () => api.get('/settings/backup/download', { responseType: 'blob' }),
  testStorage:    (data) => api.post('/settings/storage/test', data),
  applyStorage:   ()     => api.post('/settings/storage/apply'),
}

export const datacenterApi = {
  // Alle Anhänge laden (optional gefiltert nach entityType und/oder entityId)
  listAll:         (entityType, entityId) => {
    const params = {}
    if (entityType) params.entity_type = entityType
    if (entityId)   params.entity_id   = entityId
    return api.get('/datacenter/all', { params })
  },
  // Anhänge für einen konkreten Datensatz laden
  list:            (entityType, entityId) => api.get(`/datacenter/${entityType}/${entityId}`),
  upload:          (entityType, entityId, file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/datacenter/${entityType}/${entityId}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
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
  getUpdateStatus: () => api.get('/system/update-status'),
  startUpdate:     () => api.post('/system/update/start'),
  cancelUpdate:    () => api.post('/system/update/cancel'),
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
  convertToAb:      (id) => api.post(`/invoices/${id}/convert-to-ab`),
  cancel:           (id, cancel_mode) => api.post(`/invoices/${id}/cancel`, { cancel_mode }),
  sendEmail:        (id, to_email, extra_attachments = [], cc_email = '', subject = '', body_html = '') => api.post(`/invoices/${id}/send-email`, { to_email, extra_attachments, cc_email, subject, body_html }),
  bulkSendEmail:    (invoice_ids) => api.post('/invoices/bulk-send-email', { invoice_ids }),
  markPaid:       (id, data) => api.post(`/invoices/${id}/mark-paid`, data),
  convertToInvoice: (id) => api.post(`/invoices/${id}/convert-to-invoice`),

  // Zeiteinträge
  unbilledEntries: (params) => api.get('/invoices/time-entries/unbilled', { params }),

  // Rechnungsbuch
  book:           (params) => api.get('/invoices/book/list', { params }),
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

export const accountingApi = {
  listAccounts:       (params) => api.get('/accounting/accounts', { params }),
  createAccount:      (data)   => api.post('/accounting/accounts', data),
  updateAccount:      (id, data) => api.put(`/accounting/accounts/${id}`, data),
  deleteAccount:      (id)     => api.delete(`/accounting/accounts/${id}`),
  setDefaultErloes:   (id)     => api.post(`/accounting/accounts/${id}/set-default-erloes`),
  exportBmd:          (params) => api.get('/accounting/export/bmd', { params, responseType: 'blob' }),
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

// ── Anlagen (Datacenter-API, generisch über entity_type/entity_id) ────────────
export const attachmentApi = {
  list:     (entityType, entityId) => api.get(`/datacenter/${entityType}/${entityId}`),
  upload:   (entityType, entityId, formData) =>
    api.post(`/datacenter/${entityType}/${entityId}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  remove:   (attachmentId) => api.delete(`/datacenter/${attachmentId}`),
  previewUrl:  (attachmentId) => `/api/datacenter/${attachmentId}/preview`,
  downloadUrl: (attachmentId) => `/api/datacenter/${attachmentId}/download`,
}

export default api
 