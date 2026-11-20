import { defineStore } from 'pinia'

const TOKEN_KEY = 'inforadar_token'

/**
 * 登录态唯一出口：token 的读写与清除只经本 store，
 * 任何页面/组件不得直接读写 localStorage（web-frontend-plan §3.2）。
 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
  },
  actions: {
    setToken(token) {
      this.token = token
      localStorage.setItem(TOKEN_KEY, token)
    },
    clearToken() {
      this.token = ''
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
