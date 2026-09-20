<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { StyleProfile } from '../types'

const router = useRouter()
const styles = ref<StyleProfile[]>([])

onMounted(async () => {
  try {
    styles.value = await api.getStyles()
  } catch {
    styles.value = []
  }
})
</script>

<template>
  <section class="about">
    <header class="page-head">
      <button class="back" @click="router.push('/')">← 返回首页</button>
      <div class="head-txt">
        <h2>文风 · 说明</h2>
        <p class="sub">“文风”是怎么工作的，以及每一步里它起了什么作用。</p>
      </div>
      <router-link class="compare-link" to="/styles">去对比 →</router-link>
    </header>

    <div class="body">
      <section class="block">
        <h3>文风是什么</h3>
        <p>文风 = “写作的规矩 + 随机度”。每套文风都绑定了一小段<strong>系统提示词</strong>（描述该怎么写、避免什么写法）和一个<strong>生成温度</strong>（temperature）。它在每次“续写正文”时注入给模型，决定你故事的文字腔调。</p>
      </section>

      <section class="block">
        <h3>它作用在哪一步</h3>
        <ul>
          <li><b>只影响“正文生成”</b>：世界观构建、命运卡方向、一致性质检都有各自独立的提示词和温度，文风不会串过去。</li>
          <li><b>一本书锁一种文风</b>：开书时选定并随故事持久化，之后每段正文都按该文风写。</li>
          <li><b>两部分生效</b>：① 系统提示词里加入“[文风要求] + 风格描述 + 避免的写法”；② 采样温度用该文风的设定。</li>
        </ul>
      </section>

      <section class="block">
        <h3>内置文风</h3>
        <p class="muted">（数据来自后端预设，以下自动读取）</p>
        <div class="style-list">
          <div v-for="s in styles" :key="s.id" class="style-item">
            <h4>{{ s.name }}</h4>
            <p class="desc">{{ s.description }}</p>
            <p v-if="s.forbidden?.length" class="forbid">
              避免：{{ s.forbidden.join('、') }} · 温度 {{ s.temperature }}
            </p>
          </div>
        </div>
        <p v-if="!styles.length" class="muted">（预设列表加载失败，可刷新重试）</p>
      </section>

      <section class="block">
        <h3>如何体验</h3>
        <p>去 <router-link class="link" to="/styles">文风对比</router-link> 页，输入同一段素材、勾选几种文风，点“生成对比”，模型会用每种文风各改写一遍，方便横向比较腔调差异。</p>
        <p class="note">提示：对比会真实调用模型，请先在“模型”设置里完成接入；勾选的文风越多，生成耗时越长。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.about {
  max-width: 760px;
  margin: 0 auto;
}
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 14px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.back {
  flex: none;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
}
.back:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.head-txt {
  flex: 1;
}
.head-txt h2 {
  margin: 0 0 4px;
  font-size: 22px;
  color: var(--text);
}
.sub {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.compare-link {
  flex: none;
  align-self: center;
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}
.body {
  margin-top: 14px;
}
.block {
  margin-bottom: 22px;
}
.block h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text);
}
.block p,
.block li {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.8;
}
.block ul {
  margin: 4px 0;
  padding-left: 20px;
}
.block b {
  color: var(--text);
}
.muted {
  color: var(--muted);
  font-size: 13px;
}
.style-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.style-item {
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  padding: 10px 14px;
}
.style-item h4 {
  margin: 0 0 4px;
  font-size: 15px;
  color: var(--accent);
}
.style-item .desc {
  margin: 0 0 4px;
  color: var(--text);
}
.style-item .forbid {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.link {
  color: var(--accent);
  text-decoration: none;
}
.note {
  font-size: 12px;
  color: var(--muted);
}
</style>