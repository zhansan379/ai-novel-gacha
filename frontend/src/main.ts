import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
void app.use(createPinia())
app.use(router)

// 挂载前先校验持久化会话：token 有效则恢复用户名，失效则清空，保证路由守卫读到的
// isAuthenticated 反映真实状态（避免带过期 token 进入页面后才被 401 踢回）。
void (async () => {
  const auth = useAuthStore()
  await auth.bootstrap()
  app.mount('#app')
})()