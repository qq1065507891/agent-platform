<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import request from '../utils/request'

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
    const data = await request.get('/agents', {
      params: {
        page: pagination.page,
        page_size: pagination.pageSize,
        keyword: keyword.value || undefined,
        is_public: true,
      },
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
  try {
    const data = await request.post('/conversations', {
      agent_id: agentId,
    })
    Message.success('已创建会话')
    router.push(`/chat/${data.id}`)
  } catch (error: any) {
    Message.error(error?.message || '创建会话失败')
  }
}

onMounted(fetchAgents)
</script>

<template>
  <div class="agents-page">
    <div class="toolbar">
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
            <a-button type="primary" size="small">开始对话</a-button>
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

.toolbar {
  display: flex;
  justify-content: flex-end;
}

.agent-card {
  height: 180px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.desc {
  color: #6b7280;
  margin: 8px 0 16px;
}
</style>
