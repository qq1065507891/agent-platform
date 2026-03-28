<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { deleteAgent, getAgents } from '../api/agents'

interface AgentBinding {
  skill_id: string
  type?: string
}

interface AgentItem {
  id: string
  name: string
  description?: string
  prompt_template: string
  skills?: AgentBinding[]
  is_public?: boolean
  status?: string
}

const router = useRouter()
const loading = ref(false)
const keyword = ref('')
const agents = ref<AgentItem[]>([])
const deletingAgentId = ref<string>('')
const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0,
})

const onlineCount = computed(() => agents.value.filter((item) => item.status === 'online').length)

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

const onCreateAgent = () => {
  router.push('/my-agents/create')
}

const onEditAgent = (agent: AgentItem) => {
  router.push(`/my-agents/${agent.id}/edit`)
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
    <section class="hero glass-panel">
      <div>
        <div class="hero-title">我的智能体舰队</div>
        <div class="hero-subtitle">统一管理你的专属智能体，快速迭代和发布。</div>
      </div>
      <div class="hero-kpis">
        <div class="kpi-item">
          <div class="kpi-label">总数</div>
          <div class="kpi-value">{{ pagination.total }}</div>
        </div>
        <div class="kpi-item">
          <div class="kpi-label">在线</div>
          <div class="kpi-value accent">{{ onlineCount }}</div>
        </div>
      </div>
    </section>

    <div class="toolbar glass-panel">
      <a-input-search v-model="keyword" placeholder="搜索我的智能体" allow-clear @search="onSearch" />
      <a-button type="primary" @click="onCreateAgent">创建智能体</a-button>
    </div>

    <a-spin :loading="loading">
      <a-row :gutter="16">
        <a-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" :lg="6">
          <a-card class="agent-card" hoverable>
            <template #title>
              <div class="card-title">
                <span class="card-title-text">{{ agent.name }}</span>
                <a-space size="mini">
                  <a-button size="mini" type="text" @click.stop="onEditAgent(agent)">编辑</a-button>
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
                </a-space>
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

  </div>
</template>

<style scoped>
.my-agents-page {
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
  padding: 20px 22px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  background-image: linear-gradient(135deg, rgba(109, 94, 248, 0.28), rgba(39, 211, 195, 0.12));
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

.hero-kpis {
  display: flex;
  gap: 10px;
}

.kpi-item {
  min-width: 96px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.08);
}

.kpi-label {
  font-size: 12px;
  color: var(--text-3);
}

.kpi-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.kpi-value.accent {
  color: var(--accent);
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px;
}

.agent-card {
  height: 208px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
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
  color: var(--text-2);
  margin: 8px 0 12px;
}

.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-3);
}
</style>
