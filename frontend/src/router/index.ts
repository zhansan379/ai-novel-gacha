import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import StoryView from '../views/StoryView.vue'
import LoreView from '../views/LoreView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/story/:id', name: 'story', component: StoryView },
    { path: '/story/:id/lore', name: 'lore', component: LoreView },
  ],
})

export default router