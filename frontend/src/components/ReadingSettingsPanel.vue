<script setup lang="ts">
import { useReadingStore, THEME_OPTIONS, FONT_OPTIONS, PAGE_WIDTHS } from '../stores/reading'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
const store = useReadingStore()
</script>

<template>
  <Teleport to="body">
    <div v-if="props.open" class="rs-overlay" @click.self="emit('close')">
      <div class="rs-panel" role="dialog" aria-modal="true" aria-label="阅读设置">
        <header class="rs-head">
          <h3>设置</h3>
          <button class="rs-close" title="关闭 (Esc)" aria-label="关闭" @click="emit('close')">×</button>
        </header>

        <!-- 阅读主题：6 种背景色块，选中带勾号 -->
        <div class="rs-row">
          <span class="rs-label">阅读主题</span>
          <div class="rs-control">
            <button
              v-for="t in THEME_OPTIONS"
              :key="t.key"
              class="swatch"
              :class="[`swatch-${t.key}`, { sel: store.theme === t.key }]"
              :title="t.label"
              @click="store.setTheme(t.key)"
            >
              <svg v-if="store.theme === t.key" class="check" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </button>
          </div>
        </div>

        <!-- 正文字体：黑体 / 宋体 / 楷体 -->
        <div class="rs-row">
          <span class="rs-label">正文字体</span>
          <div class="rs-radio-group">
            <button
              v-for="f in FONT_OPTIONS"
              :key="f.key"
              :class="['rs-opt', { sel: store.font === f.key }]"
              @click="store.setFont(f.key)"
            >{{ f.label }}</button>
          </div>
        </div>

        <!-- 字体大小：数值加减器 -->
        <div class="rs-row">
          <span class="rs-label">字体大小</span>
          <div class="rs-step">
            <button class="step-btn" title="减小字号" @click="store.setFontSize(store.fontSize - 1)">A−</button>
            <span class="step-num">{{ store.fontSize }}</span>
            <button class="step-btn" title="增大字号" @click="store.setFontSize(store.fontSize + 1)">A+</button>
          </div>
        </div>

        <!-- 页面宽度 -->
        <div class="rs-row">
          <span class="rs-label">页面宽度</span>
          <div class="rs-radio-group">
            <button
              v-for="w in PAGE_WIDTHS"
              :key="String(w)"
              :class="['rs-opt', { sel: store.pageWidth === w }]"
              @click="store.setPageWidth(w)"
            >{{ w === 'auto' ? '自动' : w }}</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rs-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 70;
}
.rs-panel {
  width: min(480px, 94vw);
  max-height: 90vh;
  overflow: auto;
  background: #fff;
  border-radius: 0;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.25);
  animation: rs-pop 0.18s ease;
}
@keyframes rs-pop {
  from { transform: translateY(12px) scale(0.98); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.rs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #ececec;
}
.rs-head h3 { margin: 0; font-size: 16px; color: #222; }
.rs-close {
  border: none;
  background: none;
  font-size: 22px;
  color: #999;
  cursor: pointer;
  line-height: 1;
  padding: 0 2px;
}
.rs-close:hover { color: #e35d5d; }

/* 列表行：左标签 + 右控件，浅灰分割线 */
.rs-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
}
.rs-row + .rs-row { border-top: 1px solid #f2f2f2; }
.rs-label { flex: none; font-size: 14px; color: #333; }

/* 右控件容器（色块 / 单选组 / 加减器） */
.rs-control,
.rs-radio-group,
.rs-step {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

/* 色块 */
.swatch {
  width: 27px;
  height: 27px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  padding: 0;
  transition: box-shadow 0.15s, transform 0.15s;
}
.swatch + .swatch { margin-left: 9px; }
.swatch:hover { transform: translateY(-2px); }
.swatch.sel {
  box-shadow: 0 0 0 2px #e35d5d;
}
.swatch .check { color: #e35d5d; }
.swatch-dark .check { color: #fff; }
.swatch-lightgray { background: #eaebec; }
.swatch-lightred { background: #f7eceb; }
.swatch-beige { background: #f3ede1; }
.swatch-lightgreen { background: #ecf2e9; }
.swatch-lightblue { background: #e9f0f7; }
.swatch-dark { background: #222329; }

/* 单选按钮组 */
.rs-radio-group {
  flex-wrap: wrap;
  gap: 8px;
}
.rs-opt {
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: #fff;
  color: #555;
  cursor: pointer;
  font-size: 13px;
  border-radius: 0;
  transition: all 0.15s;
}
.rs-opt:hover { border-color: #e35d5d; color: #e35d5d; }
.rs-opt.sel {
  border-color: #e35d5d;
  color: #e35d5d;
  background: #fbe9e9;
  font-weight: 600;
}

/* 数值加减器 */
.rs-step { gap: 6px; }
.step-btn {
  width: 34px;
  height: 30px;
  border: 1px solid #e0e0e0;
  background: #fff;
  cursor: pointer;
  color: #333;
  font-size: 13px;
  border-radius: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.step-btn:hover { border-color: #e35d5d; color: #e35d5d; }
.step-num {
  min-width: 30px;
  text-align: center;
  font-size: 15px;
  font-weight: 600;
  color: #222;
}
</style>