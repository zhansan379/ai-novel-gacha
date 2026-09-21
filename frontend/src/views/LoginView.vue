<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

function switchMode(m: 'login' | 'register') {
  mode.value = m
  error.value = null
}

async function submit() {
  error.value = null
  const name = username.value.trim()
  if (!name || (mode.value === 'login' ? !password.value : password.value.length < 6)) {
    error.value = mode.value === 'login'
      ? '请输入用户名和密码'
      : '用户名必填，密码至少 6 位'
    return
  }
  if (mode.value === 'register' && password.value !== confirm.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  busy.value = true
  try {
    if (mode.value === 'register') await auth.register(name, password.value)
    else await auth.login(name, password.value)
    router.push({ name: 'home' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="card login-card" @submit.prevent="submit">
      <h2>AI 小说抽卡机</h2>
      <p class="sub">登录后开始写作；每位用户自带模型接入，互不影响。</p>

      <div class="tabs">
        <button type="button" :class="{ on: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button type="button" :class="{ on: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <label class="field">
        <span>用户名</span>
        <input v-model="username" autocomplete="username" placeholder="你的昵称" />
      </label>

      <label class="field">
        <span>密码</span>
        <input v-model="password" type="password" autocomplete="current-password"
               placeholder="至少 6 位" />
      </label>

      <label v-if="mode === 'register'" class="field">
        <span>确认密码</span>
        <input v-model="confirm" type="password" autocomplete="new-password" placeholder="再输一次" />
      </label>

      <p v-if="error" class="msg err">{{ error }}</p>

      <button class="btn primary" type="submit" :disabled="busy">
        {{ busy ? '提交中…' : mode === 'login' ? '登 录' : '注册并登录' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}
.login-card {
  width: min(360px, 94vw);
  padding: 28px 26px;
}
.login-card h2 { margin: 0 0 6px; font-size: 20px; }
.sub { font-size: 13px; color: var(--muted); margin: 0 0 18px; line-height: 1.5; }
.tabs {
  display: flex;
  gap: 0;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--border);
}
.tabs button {
  flex: 1;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 0;
  cursor: pointer;
  font-size: 15px;
  color: var(--muted);
  font-family: inherit;
}
.tabs button.on { color: var(--accent); border-bottom-color: var(--accent); }
.field { display: block; margin-bottom: 14px; }
.field span { display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; }
.field input {
  width: 100%; box-sizing: border-box; padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 0;
  background: var(--bg-card); color: var(--text); font-family: inherit;
}
.field input:focus { outline: none; border-color: var(--accent); }
.btn { width: 100%; padding: 11px; border: none; cursor: pointer; font-size: 15px; }
.btn.primary { background: var(--accent); color: #fff; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.msg { font-size: 13px; padding: 8px 10px; margin: 6px 0 12px; }
.msg.err { background: #fdeaea; color: #b91c1c; }
</style>