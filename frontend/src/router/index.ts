import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import StoryView from '../views/StoryView.vue'
import LoreView from '../views/LoreView.vue'
import FavoritesView from '../views/FavoritesView.vue'
import StyleCompareView from '../views/StyleCompareView.vue'
import StyleAboutView from '../views/StyleAboutView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/favorites', name: 'favorites', component: FavoritesView },
    { path: '/story/:id', name: 'story', component: StoryView },
    { path: '/story/:id/lore', name: 'lore', component: LoreView },
    { path: '/styles', name: 'style-compare', component: StyleCompareView },
    { path: '/styles/about', name: 'style-about', component: StyleAboutView },
  ],
})

export default router