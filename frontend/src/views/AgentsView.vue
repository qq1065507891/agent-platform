<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getAgents } from '../api/agents'

interface AgentItem {
  id: string
  name: string
  description?: string
  owner_id?: string
}

const router = useRouter()
const loading = ref(false)
const keyword = ref('')
const agents = ref<AgentItem[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0,
})

const fetchAgents = async () => {
  loading.value = true
  try {
    const data = await getAgents({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: keyword.value || undefined,
      is_public: true,
    })
    agents.value = data.list
    pagination.total = data.total
  } catch (error: any) {
    Message.error(error?.message || '获取智能体失败')
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  pagination.page = 1
  fetchAgents()
}

const onCreateConversation = async (agentId: string) => {
  router.push(`/agent-chat/${agentId}`)
}

onMounted(fetchAgents)
</script>

<template>
  <div class="agents-page">
    <section class="hero glass-panel">
      <div>
        <div class="hero-title">智能体市场</div>
        <div class="hero-subtitle">探索公共智能体，快速发起高质量对话。</div>
      </div>
      <a-tag color="arcoblue" bordered>Public Marketplace</a-tag>
    </section>

    <div class="toolbar glass-panel">
      <a-input-search
        v-model="keyword"
        placeholder="搜索智能体"
        allow-clear
        @search="onSearch"
      />
    </div>

    <a-spin :loading="loading">
      <a-row :gutter="16">
        <a-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" :lg="6">
          <a-card class="agent-card" hoverable @click="onCreateConversation(agent.id)">
            <template #title>{{ agent.name }}</template>
            <p class="desc">{{ agent.description || '暂无描述' }}</p>
            <a-button type="primary" size="small" @click.stop="onCreateConversation(agent.id)">开始对话</a-button>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<style scoped>
.agents-page {
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
  background-image: linear-gradient(135deg, rgba(109, 94, 248, 0.26), rgba(39, 211, 195, 0.1));
}

.hero-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-1);
}

.hero-subtitle {
  margin-top: 6px;
  color: var(--text-2);
  font-size: 13px;
}

.toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 12px;
}

.agent-card {
  height: 180px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
}

.desc {
  color: var(--text-2);
  margin: 8px 0 16px;
}
</style>
