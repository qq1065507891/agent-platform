<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { deleteAgent, getAgents } from '../api/agents'
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
const deletingAgentId = ref<string>('')
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
    agents.value = Array.isArray(data?.list) ? data.list : []
    pagination.total = Number(data?.total || 0)
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    if (detail === '会话不存在') {
      agents.value = []
      pagination.total = 0
      return
    }
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

const onDeleteAgent = (agent: AgentItem) => {
  Modal.confirm({
    title: '确认删除该智能体？',
    content: `删除后不可恢复：${agent.name}`,
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      if (deletingAgentId.value) return
      deletingAgentId.value = agent.id
      try {
        await deleteAgent(agent.id)
        Message.success('智能体已删除')
        if (agents.value.length === 1 && pagination.page > 1) {
          pagination.page -= 1
        }
        await fetchAgents()
      } catch (error: any) {
        const detail = error?.response?.data?.detail
        if (detail === '无权限') {
          Message.error('无权限删除该智能体，仅可删除自己创建的智能体')
        } else {
          Message.error(detail || error?.message || '删除失败')
        }
      } finally {
        deletingAgentId.value = ''
      }
    },
  })
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
            <template #title>
              <div class="card-title">
                <span class="card-title-text">{{ agent.name }}</span>
                <a-button
                  size="mini"
                  type="text"
                  status="danger"
                  :loading="deletingAgentId === agent.id"
                  :disabled="!!deletingAgentId && deletingAgentId !== agent.id"
                  @click.stop="onDeleteAgent(agent)"
                >
                  删除
                </a-button>
              </div>
            </template>
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

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
