<script setup lang="ts">
import { ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { Modal } from '@arco-design/web-vue'
import AgentFormPanel from './components/AgentFormPanel.vue'

const router = useRouter()
const panelRef = ref<any>()

const confirmLeaveIfDirty = async () => {
  if (!panelRef.value?.isDirty?.value) return true
  return await new Promise<boolean>((resolve) => {
    Modal.confirm({
      title: '有未保存内容，确认离开？',
      content: '离开后未保存的修改将丢失。',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}

const onSaved = () => {
  panelRef.value?.markClean?.()
  router.push('/my-agents')
}

const onCancel = async () => {
  const canLeave = await confirmLeaveIfDirty()
  if (canLeave) {
    router.push('/my-agents')
  }
}

onBeforeRouteLeave(async () => {
  return await confirmLeaveIfDirty()
})
</script>

<template>
  <div class="agent-form-page">
    <section class="hero glass-panel">
      <div>
        <div class="hero-title">创建智能体</div>
        <div class="hero-subtitle">配置基础能力与知识库，快速发布你的专属助手。</div>
      </div>
      <a-space>
        <a-button type="outline" @click="onCancel">返回我的智能体</a-button>
        <a-tag color="arcoblue" bordered class="dark-text-tag">New Agent</a-tag>
      </a-space>
    </section>

    <agent-form-panel ref="panelRef" mode="create" @saved="onSaved" @cancel="onCancel" />
  </div>
</template>

<style scoped>
.agent-form-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.glass-panel {
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
  border-radius: var(--radius-xl);
}

.hero {
  padding: 18px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background-image: linear-gradient(135deg, rgba(38, 88, 200, 0.92), rgba(58, 110, 226, 0.82));
  border: 1px solid rgba(255, 255, 255, 0.45);
}

.hero-title,
.hero-subtitle {
  color: #ffffff;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}

:deep(.hero .arco-btn-outline) {
  color: #111827 !important;
  background: rgba(255, 255, 255, 0.95) !important;
  border-color: rgba(0, 0, 0, 0.35) !important;
}

:deep(.hero .arco-btn-outline:hover) {
  background: rgba(255, 255, 255, 1) !important;
}

:deep(.hero .arco-tag),
:deep(.hero .arco-tag .arco-tag-content),
:deep(.dark-text-tag),
:deep(.dark-text-tag *) {
  color: #111827 !important;
  background: rgba(255, 255, 255, 0.95) !important;
  border-color: rgba(0, 0, 0, 0.25) !important;
}

.hero-subtitle {
  margin-top: 6px;
  color: #ffffff;
  font-size: 13px;
}
</style>
