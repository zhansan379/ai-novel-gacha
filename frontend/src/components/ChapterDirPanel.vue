<script setup lang="ts">
import { ref } from 'vue'
import { useDecisionStore } from '../stores/decision'

const store = useDecisionStore()

const emit = defineEmits<{ (e: 'jump', no: number): void; (e: 'close'): void }>()

// 内联改标题状态：editingNo 表示正在改第几章；draft 为输入草稿
const editingNo = ref<number | null>(null)
const draft = ref('')

function startEdit(no: number, currentTitle: string) {
  editingNo.value = no
  draft.value = currentTitle || ''
}
function commitEdit(no: number) {
  const t = draft.value.trim()
  if (t) store.renameChapter(no, t)
  editingNo.value = null
}
function cancelEdit() {
  editingNo.value = null
}
</script>

<template>
  <div class="dir">
    <div class="dir-head">
      <h3>章节目录</h3>
      <button class="dir-close" aria-label="关闭" @click="emit('close')">✕</button>
    </div>
    <p v-if="!store.chapters.length" class="dir-empty">还没有章节。</p>
    <ol class="dir-list">
      <li v-for="c in store.chapters" :key="c.no" class="dir-item">
        <button class="dir-jump" @click="emit('jump', c.no)">
          <span class="dir-no">{{ c.no }}</span>
          <span class="dir-title">{{ c.title || `第 ${c.no} 章` }}</span>
          <span class="dir-range">{{ c.passage_from }}~{{ c.passage_to || '…' }}</span>
          <span v-if="c.is_final" class="dir-final">结局</span>
        </button>
        <span v-if="editingNo === c.no" class="dir-edit">
          <input
            v-model="draft"
            class="dir-input"
            maxlength="60"
            :placeholder="`第 ${c.no} 章标题`"
            @keydown.enter="commitEdit(c.no)"
            @keydown.esc="cancelEdit"
          />
          <button class="dir-mini" @click="commitEdit(c.no)">保存</button>
          <button class="dir-mini" @click="cancelEdit">取消</button>
        </span>
        <button v-else class="dir-edit-btn" title="改标题" @click="startEdit(c.no, c.title)">✎</button>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.dir {
  background: var(--bg-card);
  border: 1px solid var(--border);
  box-shadow: 0 12px 40px rgba(40, 33, 20, 0.22);
  padding: 18px 20px;
  max-height: 78vh;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.dir-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.dir-head h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text);
}
.dir-close {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 15px;
  cursor: pointer;
  padding: 4px;
}
.dir-close:hover {
  color: var(--accent);
}
.dir-empty {
  color: var(--muted);
  font-size: 14px;
}
.dir-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.dir-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 2px;
  border-bottom: 1px dashed var(--border);
}
.dir-jump {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  padding: 2px 0;
  min-width: 0;
}
.dir-jump:hover .dir-title {
  color: var(--accent);
}
.dir-no {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
}
.dir-title {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.dir-range {
  color: var(--muted);
  font-size: 12px;
  flex: 0 0 auto;
}
.dir-final {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--bg-card);
  background: var(--accent);
  border-radius: 3px;
  padding: 1px 5px;
}
.dir-edit {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dir-input {
  width: 150px;
  padding: 3px 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
}
.dir-mini {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
}
.dir-mini:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.dir-edit-btn {
  flex: 0 0 auto;
  border: none;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
}
.dir-edit-btn:hover {
  color: var(--accent);
}
</style>