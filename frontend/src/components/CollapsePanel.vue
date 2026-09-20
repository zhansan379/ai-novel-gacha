<script setup lang="ts">
import { ref } from 'vue'

// 自定义折叠面板：自管展开状态（默认收起）。open 仅作为初始展开状态。
// 展开/收起用 grid-template-rows 0fr↔1fr 做高度动画，兼容任意内容高度。
// 注意：open 是命中各面板的默认收起状态，父组件不必传该属性。
const props = defineProps<{
  title: string
  open?: boolean
}>()

const isOpen = ref(props.open ?? false)

function toggle() {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <section class="cp">
    <button
      type="button"
      class="cp-head"
      :class="{ on: isOpen }"
      :aria-expanded="isOpen"
      @click="toggle"
    >
      <span class="cp-title">{{ title }}</span>
      <span class="cp-hint"><slot name="hint" /></span>
      <svg class="cp-chev" viewBox="0 0 24 24" width="16" height="16" fill="none"
           stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
           aria-hidden="true">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
    <!-- 用 open 类常驻驱动 grid 行高动画；收起时 0fr + overflow:hidden + opacity:0 即不可见 -->
    <div class="cp-body" :class="{ open: isOpen }">
      <div class="cp-inner">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.cp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: none;
  background: none;
  padding: 2px 0;
  font-family: inherit;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}
.cp-title {
  line-height: 1.5;
}
.cp-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
  white-space: nowrap;
}
.cp-chev {
  flex: none;
  margin-left: auto;
  color: var(--muted);
  transition: transform 0.22s ease, color 0.2s ease;
}
.cp-head:hover .cp-chev {
  color: var(--accent);
}
.cp-head.on .cp-chev {
  transform: rotate(180deg);
  color: var(--accent);
}
.cp-body {
  display: grid;
  grid-template-rows: 0fr;
  overflow: hidden;
  opacity: 0;
  transition: grid-template-rows 0.24s ease, opacity 0.2s ease;
}
.cp-body.open {
  grid-template-rows: 1fr;
  opacity: 1;
}
.cp-inner {
  min-height: 0;
  overflow: hidden;
}
</style>