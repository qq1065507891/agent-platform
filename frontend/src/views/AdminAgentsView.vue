<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { deleteAgent, getAgents } from '../api/agents'

interface AgentItem {
  id: string
  name: string
  description?: string
  owner_id?: string
  owner_username?: string
  owner_email?: string
  is_public?: boolean
  status?: string
  created_at?: string
}

const loading = ref(false)
const keyword = ref('')
const onlyPublic = ref(false)
const deletingAgentId = ref('')
const agents = ref<AgentItem[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0,
})

const formatDate = (value?: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const formatOwner = (agent: AgentItem) => {
  const username = agent.owner_username?.trim()
  const email = agent.owner_email?.trim()
  if (username && email) return `${username}（${email}）`
  if (username) return username
  if (email) return email
  return agent.owner_id || '-'
}

const fetchAgents = async () => {
  loading.value = true
  try {
    const data = await getAgents({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: keyword.value || undefined,
      is_public: onlyPublic.value ? true : undefined,
    })
    agents.value = Array.isArray(data?.list) ? data.list : []
    pagination.total = Number(data?.total || 0)
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

const onPageChange = (page: number) => {
  pagination.page = page
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
        Message.error(detail || error?.message || '删除失败')
      } finally {
        deletingAgentId.value = ''
      }
    },
  })
}

onMounted(fetchAgents)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <div class="title">智能体管理</div>
        <div class="subtitle">管理员可查看并删除全部智能体</div>
      </div>
    </div>

    <div class="toolbar">
      <a-input-search v-model="keyword" placeholder="搜索智能体名称" allow-clear @search="onSearch" />
      <a-checkbox v-model="onlyPublic" @change="onSearch">仅看公开</a-checkbox>
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
            <div class="meta-row">
              <span>创建者：{{ formatOwner(agent) }}</span>
              <span>公开：{{ agent.is_public ? '是' : '否' }}</span>
            </div>
            <div class="meta-row">
              <span>状态：{{ agent.status || 'draft' }}</span>
              <span>创建时间：{{ formatDate(agent.created_at) }}</span>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>

    <div class="pagination">
      <a-pagination
        :current="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        show-total
        @change="onPageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.admin-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.subtitle {
  color: #6b7280;
  font-size: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-card {
  height: 220px;
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

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: #4b5563;
}

.pagination {
  display: flex;
  justify-content: flex-end;
}
</style>
