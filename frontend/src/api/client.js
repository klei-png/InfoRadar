const TOKEN_KEY = 'inforradar_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

async function request(url, opts = {}) {
  const headers = { Authorization: `Bearer ${getToken()}`, ...opts.headers }
  if (opts.body) headers['Content-Type'] = 'application/json'
  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401) {
    clearToken()
    location.hash = '#/login'
    throw new Error('unauthorized')
  }
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json()
}

export const api = {
  login: (username, password) =>
    request('/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  digests: (days = 7) => request(`/digests?days=${days}`),
  digestFull: (category) => request(`/digests/${category}`),
  items: (minScore = 6, limit = 30) => request(`/items?min_score=${minScore}&limit=${limit}`),
  ask: (question) => request('/ask', { method: 'POST', body: JSON.stringify({ question }) }),
  feedback: (itemId, rating) =>
    request('/feedback', {
      method: 'POST',
      body: JSON.stringify({ item_id: itemId, rating }),
    }),
}
