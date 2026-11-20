import { request } from './http'

export function login(username, password) {
  return request('/login', { method: 'POST', body: { username, password } })
}
