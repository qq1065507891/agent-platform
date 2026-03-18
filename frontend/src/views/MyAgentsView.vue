<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getAgents } from '../api/agents'
import AgentFormDrawer from './components/AgentFormDrawer.vue'

interface AgentItem {
  id: string
  name: string
  description?: string
  prompt_template: string
  is_public?: boolean
  status?: string
}

const loading = ref(false)
const keyword = ref('')
const agents = ref<AgentItem[]>([])
const drawerVisible = ref(false)
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
      mine: true,
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

const onCreated = () => {
  drawerVisible.value = false
  fetchAgents()
}

onMounted(fetchAgents)
</script>

<template>
  <div class="my-agents-page">
    <div class="toolbar">
      <a-input-search v-model="keyword" placeholder="搜索我的智能体" allow-clear @search="onSearch" />
      <a-button type="primary" @click="drawerVisible = true">创建智能体</a-button>
    </div>

    <a-spin :loading="loading">
      <a-row :gutter="16">
        <a-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" :lg="6">
          <a-card class="agent-card" hoverable>
            <template #title>{{ agent.name }}</template>
            <p class="desc">{{ agent.description || '暂无描述' }}</p>
            <div class="meta">
              <span>状态：{{ agent.status || 'draft' }}</span>
              <span>公开：{{ agent.is_public ? '是' : '否' }}</span>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>

    <agent-form-drawer v-model:visible="drawerVisible" @created="onCreated" />
  </div>
</template>

<style scoped>
.my-agents-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.agent-card {
  height: 200px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.desc {
  color: #6b7280;
  margin: 8px 0 12px;
}

.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #4b5563;
}
</style>
