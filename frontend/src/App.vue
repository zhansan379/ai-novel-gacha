<script setup lang="ts"></script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="brand">命运抽卡 · AI 小说</router-link>
      <span class="tagline">抽卡 / 自由输入决定剧情走向</span>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 14px 24px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}
.brand {
  font-weight: 700;
  font-size: 18px;
  color: #1f2937;
  text-decoration: none;
}
.tagline {
  color: #9ca3af;
  font-size: 13px;
}
.app-main {
  max-width: 960px;
  margin: 24px auto;
  padding: 0 16px;
}
</style>