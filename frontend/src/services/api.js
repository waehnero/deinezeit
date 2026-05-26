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
  download_blob:   (id) => api.get(`/datacenter/${id}/download`, { responseType: 'blob' }),
  createShareLink: (id, expiresHours) => api.post(`/datacenter/${id}/share-link`, { expires_hours: expiresHours }),
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

export default api
