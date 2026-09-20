import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ReadingTheme = 'lightgray' | 'lightred' | 'beige' | 'lightgreen' | 'lightblue' | 'dark'
export type ReadingFont = 'sans' | 'song' | 'kai'
export type PageWidth = 'auto' | number

export const THEME_OPTIONS: { key: ReadingTheme; label: string }[] = [
  { key: 'lightgray', label: '浅灰' },
  { key: 'lightred', label: '浅红' },
  { key: 'beige', label: '米黄' },
  { key: 'lightgreen', label: '浅绿' },
  { key: 'lightblue', label: '浅蓝' },
  { key: 'dark', label: '深黑' },
]

export const FONT_OPTIONS: { key: ReadingFont; label: string }[] = [
  { key: 'sans', label: '黑体' },
  { key: 'song', label: '宋体' },
  { key: 'kai', label: '楷体' },
]

export const PAGE_WIDTHS: PageWidth[] = ['auto', 640, 800, 900, 1000, 1280]

// 每套主题的全局 CSS 变量（page 背景 / card 卡片 / 文本 / 次要文本 / 边框 / 强调底 / 强调色 / 强调色上的文字色）
// 卡片底色取"比页面背景浅一点的同色系"，而不是纯白
const THEME_VARS: Record<ReadingTheme, Record<string, string>> = {
  lightgray: { page: '#eaebec', card: '#f3f3f4', text: '#2f2f34', muted: '#6f7075', border: '#d9dadd', soft: '#f0f0f2', accent: '#8a6a3b', onAccent: '#fffdf6' },
  lightred: { page: '#f7eceb', card: '#fbf2f1', text: '#3b2f2e', muted: '#867b79', border: '#ebd8d5', soft: '#fbecea', accent: '#c25e5e', onAccent: '#fffdf6' },
  beige: { page: '#f3ede1', card: '#f8f3e8', text: '#2b2620', muted: '#7a6f5f', border: '#e4dccb', soft: '#f2e9d8', accent: '#8a6a3b', onAccent: '#fffdf6' },
  lightgreen: { page: '#ecf2e9', card: '#f2f6ef', text: '#2f362f', muted: '#75806e', border: '#dbe4d7', soft: '#ecf2e7', accent: '#6f8f5f', onAccent: '#fffdf6' },
  lightblue: { page: '#e9f0f7', card: '#f0f5fa', text: '#2f333a', muted: '#6f7882', border: '#d9e1ec', soft: '#eaf1f8', accent: '#4a6f9e', onAccent: '#fffdf6' },
  dark: { page: '#191a1f', card: '#222329', text: '#f1f1f4', muted: '#a6a8b0', border: '#34353d', soft: '#2b2c33', accent: '#d4b06a', onAccent: '#191a1f' },
}

const FONT_CSS: Record<ReadingFont, string> = {
  sans: `-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif`,
  song: `Georgia, 'Times New Roman', 'SimSun', 'Songti SC', '宋体', serif`,
  kai: `'KaiTi', 'STKaiti', 'Kaiti SC', '楷体', serif`,
}

const STORAGE_KEY = 'reading-settings-v1'

export const useReadingStore = defineStore('reading', () => {
  const theme = ref<ReadingTheme>('lightred')
  const font = ref<ReadingFont>('sans')
  const fontSize = ref(18)
  const pageWidth = ref<PageWidth>(800)
  // 记忆最近一次非深黑主题，供日间/夜间一键切换回来
  const prevLightTheme = ref<ReadingTheme>('lightred')

  // 回读本地持久化
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>
    if (saved.theme && THEME_OPTIONS.some((t) => t.key === saved.theme)) theme.value = saved.theme as ReadingTheme
    if (saved.font && FONT_OPTIONS.some((f) => f.key === saved.font)) font.value = saved.font as ReadingFont
    if (typeof saved.fontSize === 'number') fontSize.value = Math.min(30, Math.max(12, saved.fontSize))
    if (saved.pageWidth === 'auto' || PAGE_WIDTHS.includes(saved.pageWidth as PageWidth)) pageWidth.value = saved.pageWidth as PageWidth
  } catch { /* 首次使用或缺省时走默认值 */ }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ theme: theme.value, font: font.value, fontSize: fontSize.value, pageWidth: pageWidth.value }))
    } catch { /* 隐私模式等场景静默 */ }
  }

  function apply() {
    persist()
    const root = document.documentElement
    const v = THEME_VARS[theme.value]
    root.style.setProperty('--bg-page', v.page)
    root.style.setProperty('--bg-card', v.card)
    root.style.setProperty('--text', v.text)
    root.style.setProperty('--muted', v.muted)
    root.style.setProperty('--border', v.border)
    root.style.setProperty('--accent-soft', v.soft)
    root.style.setProperty('--accent', v.accent)
    root.style.setProperty('--on-accent', v.onAccent)
    root.style.setProperty('--reader-font', FONT_CSS[font.value])
    root.style.setProperty('--reader-font-size', fontSize.value + 'px')
    root.style.setProperty('--reader-width', pageWidth.value === 'auto' ? 'auto' : pageWidth.value + 'px')
  }

  watch([theme, font, fontSize, pageWidth], apply, { immediate: true })

  function setTheme(k: ReadingTheme) { theme.value = k }
  function setFont(k: ReadingFont) { font.value = k }
  function setFontSize(n: number) { fontSize.value = Math.min(30, Math.max(12, n)) }
  function setPageWidth(w: PageWidth) { pageWidth.value = w }

  const isNight = computed(() => theme.value === 'dark')
  /** 日间/夜间一键切换：夜间切回最近一次非深黑主题；日间记录当前并切到深黑 */
  function toggleNight() {
    if (theme.value === 'dark') {
      theme.value = prevLightTheme.value
    } else {
      prevLightTheme.value = theme.value
      theme.value = 'dark'
    }
  }

  return { theme, font, fontSize, pageWidth, isNight, setTheme, setFont, setFontSize, setPageWidth, toggleNight }
})