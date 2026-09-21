/**
 * 会话状态：token 存 localStorage，提供登录/注册/登出与"是否已登录/当前用户名"。
 * 所有业务请求由 api client 自动附带 Authorization 头。
 */
import { defineStore } from 'pinia'
import { api, getToken } from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken() as string,
    username: (localStorage.getItem('cn_username') ?? '') as string,
    ready: false, // 启动时是否已完成一次 /auth/me 校验
  }),
  getters: {
    isAuthenticated: (s) => Boolean(s.token),
  },
  actions: {
    /** 启动校验：token 有效则刷新用户名，失效则清空。失败不抛错（登录页兜底）。 */
    async bootstrap() {
      if (!this.token) {
        this.ready = true
        return
      }
      try {
        const me = await api.me()
        this.username = me.username
      } catch {
        this.token = ''
        this.username = ''
        localStorage.removeItem('cn_token')
        localStorage.removeItem('cn_username')
      } finally {
        this.ready = true
      }
    },
    async login(username: string, password: string) {
      const r = await api.login(username, password)
      this._apply(r.token, r.username)
    },
    async register(username: string, password: string) {
      const r = await api.register(username, password)
      this._apply(r.token, r.username)
    },
    async logout() {
      try {
        await api.logout()
      } catch {
        /* 尽力而为：本地会话始终清除 */
      }
      this._clear()
    },
    _apply(token: string, username: string) {
      this.token = token
      this.username = username
      localStorage.setItem('cn_token', token)
      localStorage.setItem('cn_username', username)
    },
    _clear() {
      this.token = ''
      this.username = ''
      localStorage.removeItem('cn_token')
      localStorage.removeItem('cn_username')
    },
  },
})