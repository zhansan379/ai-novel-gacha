<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useDecisionStore } from '../stores/decision'
import type { StyleProfile } from '../types'

const router = useRouter()
const store = useDecisionStore()
const premise = ref('')
const styles = ref<StyleProfile[]>([])
const selectedStyle = ref<string>('')

// 开书阶段提示（本地时序切换，非真实后端进度，仅供视觉反馈）
const PHASES = ['构建世界观与角色', '埋伏笔 · 织历史线', '抽取首轮命运卡', '撰写开篇正文']
const phase = ref(PHASES[0])
let phaseTimer: number | undefined

watch(() => store.loading, (loading) => {
  clearInterval(phaseTimer)
  if (loading) {
    let i = 0
    phase.value = PHASES[i]
    phaseTimer = window.setInterval(() => {
      i = (i + 1) % PHASES.length
      phase.value = PHASES[i]
    }, 1100)
  } else {
    phase.value = PHASES[0]
  }
})

onMounted(async () => {
  try {
    styles.value = await api.getStyles()
    selectedStyle.value = styles.value[0]?.id ?? ''
  } catch {
    styles.value = []
  }
})

async function createStory() {
  if (store.loading) return
  await store.create(
    premise.value || '一个少年在雨夜的旧城、被迫背负一个不为人知的秘密',
    selectedStyle.value || undefined,
  )
  if (store.storyId) {
    router.push({ name: 'story', params: { id: store.storyId } })
  }
}
</script>

<template>
  <section class="home">
    <div class="home-inner">
      <h1 class="hero-title"><span class="hl">命运抽卡</span> · AI 互动小说</h1>
      <p class="sub">
        输入一句灵感，系统先为你构建世界观、历史与大纲；每个剧情分歧点，你可以
        <strong>抽一张命运卡</strong> 或用 <strong>自由输入</strong> 决定故事去向。
      </p>

      <div class="cta">
        <input
          v-model="premise"
          class="premise-input"
          maxlength="200"
          placeholder="例：一个失忆的杀手想找回身份……（留空则随机开书）"
        />
        <button class="btn primary big" :disabled="store.loading" @click="createStory">
          {{ store.loading ? '开书中…' : '抽 卡 开 书' }}
        </button>
      </div>

      <div v-if="store.loading" class="opening">
        <span class="spinner" aria-hidden="true"></span>
        <span class="phase">{{ phase }}</span>
        <span class="dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span>
      </div>

      <div class="style-row">
        <label class="style-label" for="style">文风：</label>
        <select v-model="selectedStyle" id="style" class="style-select">
          <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <span class="style-desc">{{ styles.find((s) => s.id === selectedStyle)?.description }}</span>
      </div>

      <p v-if="store.error" class="error">{{ store.error }}</p>
      <p class="note">MVP：开书 → 设定/大纲 → 抽卡 → 正文流式 → 质检已可跑通（需在设置面板配置模型）。</p>
    </div>
  </section>
</template>

<style scoped>
.home {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  position: relative;
}
.home-inner {
  width: 100%;
  text-align: center;
  animation: fadeUp 0.5s ease both;
}
@keyframes fadeUp {
  from { transform: translateY(14px); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.hero-title {
  font-size: 34px;
  margin: 0 0 12px;
  letter-spacing: 1px;
  color: #3a3124;
  font-weight: 800;
}
/* 签名细节：关键短语下划线高亮，单一强调色 */
.hl {
  background: linear-gradient(transparent 64%, var(--accent-soft) 0);
  padding: 0 3px;
  color: var(--accent);
  font-weight: 800;
}
.sub {
  max-width: 640px;
  margin: 0 auto 26px;
  color: var(--muted);
}
.cta {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.premise-input {
  width: min(520px, 66vw);
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 15px;
  background: var(--bg-card);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.premise-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(138, 106, 59, 0.18);
}
.btn {
  padding: 12px 26px;
  border: none;
  border-radius: 10px;
  cursor: pointer;
}
.btn.primary {
  background: var(--accent);
  color: #fffdf6;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(138, 106, 59, 0.3);
  transition: background-color 0.15s, transform 0.15s, box-shadow 0.2s;
}
.btn.primary:hover:not(:disabled) {
  background: #75572f;
  transform: translateY(-2px);
}
.btn.primary:active:not(:disabled) {
  transform: translateY(0);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.style-row {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted);
  font-size: 14px;
}
.style-select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
}
.style-desc {
  max-width: 420px;
  text-align: left;
  color: #a89782;
  font-size: 13px;
}
.error {
  color: #b0452e;
}
.opening {
  margin-top: 18px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 14px;
  min-height: 22px;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex: none;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.phase {
  color: #3a3124;
  font-weight: 500;
}
.dots i {
  font-style: normal;
  animation: blink 1.4s infinite;
}
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
}
.note {
  margin-top: 34px;
  color: #a89782;
  font-size: 13px;
}
@media (max-width: 640px) {
  .cta {
    flex-direction: column;
    align-items: center;
  }
  .premise-input {
    width: 100%;
    max-width: 92vw;
  }
}
</style>