import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import HomeView from '../views/HomeView.vue'
import StoryView from '../views/StoryView.vue'
import LoreView from '../views/LoreView.vue'
import FavoritesView from '../views/FavoritesView.vue'
import LoginView from '../views/LoginView.vue'
import StyleCompareView from '../views/StyleCompareView.vue'
import StyleAboutView from '../views/StyleAboutView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', name: 'home', component: HomeView },
    { path: '/favorites', name: 'favorites', component: FavoritesView },
    { path: '/story/:id', name: 'story', component: StoryView },
    { path: '/story/:id/lore', name: 'lore', component: LoreView },
    { path: '/styles', name: 'style-compare', component: StyleCompareView },
    { path: '/styles/about', name: 'style-about', component: StyleAboutView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 全局守卫：未登录一律跳登录页；已登录访问登录页则回首页。
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.name !== 'login' && !auth.isAuthenticated) return { name: 'login' }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'home' }
  return true
})

export default router