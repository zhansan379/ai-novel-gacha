<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { ModelsConfig } from '../types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const PRESETS: { provider: string; base: string; placeholder: string }[] = [
  { provider: 'deepseek', base: 'https://api.deepseek.com/v1', placeholder: 'deepseek-chat' },
  { provider: 'openai', base: 'https://api.openai.com/v1', placeholder: 'gpt-4o-mini' },
  { provider: 'moonshot', base: 'https://api.moonshot.ai/v1', placeholder: 'kimi-k2-thinking' },
  { provider: 'groq', base: 'https://api.groq.com/openai/v1', placeholder: 'llama-3.3-70b-versatile' },
  { provider: 'ollama', base: 'http://localhost:11434/v1', placeholder: 'qwen2.5' },
]

const provider = ref('deepseek')
const model = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const config = ref<ModelsConfig | null>(null)
const saving = ref(false)
const clearing = ref(false)
const error = ref<string | null>(null)
const ok = ref('')

onMounted(load)
watch(() => props.open, (o) => { if (o) load() })

async function load() {
  try {
    config.value = await api.getModelsConfig()
    provider.value = config.value.provider || 'deepseek'
    model.value = ''
    baseUrl.value = ''
    apiKey.value = ''
  } catch (e) { error.value = msg(e) }
}

function applyPreset() {
  const p = PRESETS.find((x) => x.provider === provider.value)
  baseUrl.value = p?.base ?? ''
  if (!model.value) model.value = p?.placeholder ?? ''
  ok.value = ''
  error.value = null
}

async function save() {
  if (!model.value.trim()) { error.value = '请填写模型名'; return }
  saving.value = true
  error.value = null
  ok.value = ''
  try {
    config.value = await api.saveModelsConfig({
      provider: provider.value.trim(), model: model.value.trim(),
      base_url: baseUrl.value.trim(), api_key: apiKey.value.trim(),
    })
    ok.value = config.value.mode === 'openai-compat'
      ? '已连接真实模型'
      : '配置已保存'
    apiKey.value = ''
  } catch (e) { error.value = msg(e) } finally { saving.value = false }
}

async function clear() {
  clearing.value = true
  error.value = null
  ok.value = ''
  try {
    config.value = await api.clearModelsConfig()
    ok.value = '已回到本地 mock'
  } catch (e) { error.value = msg(e) } finally { clearing.value = false }
}

function msg(e: unknown) { return e instanceof Error ? e.message : String(e) }
</script>

<template>
  <Teleport to="body">
    <div v-if="props.open" class="overlay" @click.self="emit('close')">
      <div class="panel">
        <header class="head">
          <h3>模型接入配置</h3>
          <span class="mode" :class="config?.mode === 'openai-compat' ? 'on' : 'off'">
            {{ config?.mode === 'openai-compat' ? '真实模型' : '本地 Mock' }}
          </span>
          <button class="close" @click="emit('close')">×</button>
        </header>

        <div v-if="error" class="msg err">{{ error }}</div>
        <div v-if="ok" class="msg ok">{{ ok }}</div>

        <label class="field">
          <span>服务商</span>
          <select v-model="provider" @change="applyPreset">
            <option v-for="p in PRESETS" :key="p.provider" :value="p.provider">{{ p.provider }}</option>
          </select>
        </label>

        <label class="field">
          <span>模型名</span>
          <input v-model="model" :placeholder="PRESETS.find((p) => p.provider === provider)?.placeholder" />
        </label>

        <label class="field">
          <span>Base URL（留空自动补齐）</span>
          <input v-model="baseUrl" placeholder="https://api.deepseek.com/v1" />
        </label>

        <label class="field">
          <span>API Key（仅提交，不在界面显示明文）</span>
          <input v-model="apiKey" type="password" placeholder="sk-..." autocomplete="off" />
        </label>

        <div class="actions">
          <button class="btn primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存并连接' }}
          </button>
          <button class="btn ghost" :disabled="clearing" @click="clear">清除配置</button>
        </div>
        <p class="hint">保存后 Key 持久化到后端（SQLite），但查询接口不回传明文；未配置时自动用本地 Mock 演示。</p>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.panel {
  width: min(420px, 92vw);
  background: #fff;
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.25);
  animation: pop .18s ease;
}
@keyframes pop {
  from { transform: translateY(12px) scale(.98); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.head h3 { margin: 0; font-size: 17px; }
.mode { font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.mode.on { background: #d1fae5; color: #047857; }
.mode.off { background: #f3f4f6; color: #6b7280; }
.close { margin-left: auto; border: none; background: none; font-size: 22px; cursor: pointer; color: #9ca3af; }
.field { display: block; margin-bottom: 12px; }
.field span { display: block; font-size: 13px; color: #6b7280; margin-bottom: 4px; }
.field input, .field select {
  width: 100%; box-sizing: border-box; padding: 8px 10px;
  border: 1px solid #d1d5db; border-radius: 8px; font-family: inherit;
}
.actions { display: flex; gap: 10px; margin-top: 14px; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer; }
.btn.primary { background: #1f2937; color: #fff; }
.btn.ghost { background: #f3f4f6; color: #4b5563; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.msg { font-size: 13px; margin-bottom: 10px; padding: 8px 10px; border-radius: 6px; }
.msg.err { background: #fee2e2; color: #b91c1c; }
.msg.ok { background: #ecfdf5; color: #047857; }
.hint { font-size: 12px; color: #9ca3af; margin: 12px 0 0; line-height: 1.5; }
</style>