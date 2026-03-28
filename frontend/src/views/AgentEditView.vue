<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { getAgentDetail } from '../api/agents'
import AgentFormPanel from './components/AgentFormPanel.vue'

interface AgentBinding {
  skill_id: string
  type?: string
}

interface AgentItem {
  id: string
  name: string
  description?: string
  prompt_template: string
  is_public?: boolean
  skills?: AgentBinding[]
}

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const agent = ref<AgentItem | null>(null)
const panelRef = ref<any>()

const agentSummary = computed(() => {
  if (!agent.value) return ''
  const parts = [agent.value.id]
  if (agent.value.is_public) parts.push('公开')
  return parts.join(' · ')
})

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

const fetchAgent = async () => {
  const id = String(route.params.id || '')
  if (!id) {
    Message.error('缺少智能体 ID')
    router.push('/my-agents')
    return
  }

  loading.value = true
  try {
    const data = await getAgentDetail(id)
    agent.value = data
  } catch (error: any) {
    Message.error(error?.message || '获取智能体详情失败')
    router.push('/my-agents')
  } finally {
    loading.value = false
  }
}

const onSaved = () => {
  panelRef.value?.markClean?.()
  fetchAgent()
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

onMounted(fetchAgent)
</script>

<template>
  <div class="agent-form-page">
    <section class="hero glass-panel">
      <div>
        <div class="hero-title">编辑智能体</div>
        <div class="hero-subtitle">优化提示词、能力绑定与知识库，让智能体表现更稳定。</div>
      </div>
      <a-space size="mini">
        <a-button type="outline" @click="onCancel">返回我的智能体</a-button>
        <a-tag color="purple" bordered>Edit Agent</a-tag>
        <a-tag v-if="agentSummary" bordered>{{ agentSummary }}</a-tag>
      </a-space>
    </section>

    <a-spin :loading="loading">
      <agent-form-panel
        v-if="agent"
        ref="panelRef"
        mode="edit"
        :agent="agent"
        @saved="onSaved"
        @cancel="onCancel"
      />
    </a-spin>
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

.hero-subtitle {
  margin-top: 6px;
  font-size: 13px;
}

:deep(.hero .arco-btn-outline) {
  color: #111827 !important;
  background: rgba(255, 255, 255, 0.92) !important;
  border-color: rgba(0, 0, 0, 0.35) !important;
}

:deep(.hero .arco-btn-outline:hover) {
  background: rgba(8, 20, 46, 0.65) !important;
}

:deep(.hero .arco-tag),
:deep(.hero .arco-tag .arco-tag-content) {
  color: #111827 !important;
  background: rgba(255, 255, 255, 0.95) !important;
  border-color: rgba(0, 0, 0, 0.25) !important;
}
</style>
