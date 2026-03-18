<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import request from '../utils/request'
import { getAgentDetail, listUserConversations } from '../api/agents'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Conversation {
  id: string
  agent_id: string
  messages: ChatMessage[]
  agent_name?: string
  agent_description?: string
  created_at?: string
}

interface AgentInfo {
  id: string
  name: string
  description?: string
}

const route = useRoute()
const router = useRouter()
const conversationId = computed(() => String(route.params.id || ''))
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const conversation = ref<Conversation | null>(null)
const agentInfo = ref<AgentInfo | null>(null)
const historyList = ref<Conversation[]>([])
const expandedAgents = ref<Record<string, boolean>>({})
const messages = computed(() => conversation.value?.messages ?? [])

const historyGroups = computed(() => {
  const map: Record<string, { agent_id: string; agent_name?: string; agent_description?: string; items: Conversation[] }> = {}
  historyList.value.forEach((item) => {
    const key = item.agent_id
    if (!map[key]) {
      map[key] = {
        agent_id: item.agent_id,
        agent_name: item.agent_name,
        agent_description: item.agent_description,
        items: [],
      }
    }
    map[key].items.push(item)
  })
  return Object.values(map).map((group) => ({
    ...group,
    items: group.items.sort((a, b) => (a.id > b.id ? -1 : 1)),
  }))
})

const toggleAgentGroup = (agentId: string) => {
  expandedAgents.value[agentId] = !expandedAgents.value[agentId]
}

const formatTimestamp = (value?: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const fetchConversation = async () => {
  if (!conversationId.value || conversationId.value === 'placeholder') return
  loading.value = true
  try {
    const data = await request.get(`/conversations/${conversationId.value}`)
    conversation.value = data
    if (data?.agent_id) {
      agentInfo.value = await getAgentDetail(data.agent_id)
    }
  } catch (error: any) {
    Message.error(error?.message || '加载会话失败')
  } finally {
    loading.value = false
  }
}

const fetchHistoryList = async () => {
  try {
    const data = await listUserConversations()
    historyList.value = data
  } catch (error: any) {
    Message.error(error?.message || '加载历史对话失败')
  }
}

const selectConversation = (item: Conversation) => {
  if (!item?.id) return
  router.push(`/chat/${item.id}`)
}

const sendMessage = async () => {
  if (!conversationId.value || conversationId.value === 'placeholder') {
    Message.warning('请先在智能体市场创建会话')
    return
  }
  if (!input.value.trim()) {
    Message.warning('请输入消息')
    return
  }
  const content = input.value
  input.value = ''
  conversation.value?.messages.push({ role: 'user', content })
  sending.value = true
  try {
    const data = await request.post(`/conversations/${conversationId.value}/messages`, {
      content,
      attachments: [],
    })
    conversation.value?.messages.push({ role: 'assistant', content: data.assistant_message })
  } catch (error: any) {
    Message.error(error?.message || '发送失败')
  } finally {
    sending.value = false
  }
}

onMounted(() => {
  fetchConversation()
  fetchHistoryList()
})

watch(
  () => conversationId.value,
  () => {
    conversation.value = null
    fetchConversation()
    fetchHistoryList()
  }
)
</script>

<template>
  <div class="chat-page">
    <a-spin :loading="loading" class="chat-shell">
      <div class="chat-sidebar">
        <div class="sidebar-title">历史对话</div>
        <div v-if="historyGroups.length" class="history-list">
          <div v-for="group in historyGroups" :key="group.agent_id" class="history-group">
            <div class="history-group-header" @click="toggleAgentGroup(group.agent_id)">
              <div class="history-group-main">
                <div class="history-avatar">{{ group.agent_name?.charAt(0) || 'A' }}</div>
                <div class="history-info">
                  <div class="history-title">{{ group.agent_name || '智能体' }}</div>
                  <div class="history-meta">{{ group.agent_description || '点击展开历史' }}</div>
                </div>
              </div>
              <a-button
                size="mini"
                type="outline"
                class="history-toggle"
                @click.stop="toggleAgentGroup(group.agent_id)"
              >
                {{ expandedAgents[group.agent_id] ? '收起' : '展开' }}
              </a-button>
            </div>
            <div v-if="expandedAgents[group.agent_id]" class="history-items">
              <div
                v-for="item in group.items"
                :key="item.id"
                class="history-item"
                @click="selectConversation(item)"
              >
                <div class="history-title">会话 {{ item.id.slice(0, 6) }}</div>
                <div class="history-meta">{{ formatTimestamp(item.created_at) }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="placeholder">当前暂无历史对话</div>
      </div>

      <div class="chat-main">
        <div class="agent-header">
          <div class="agent-avatar">{{ agentInfo?.name?.charAt(0) || 'A' }}</div>
          <div class="agent-meta">
            <div class="agent-name">{{ agentInfo?.name || '未选择智能体' }}</div>
            <div class="agent-desc">{{ agentInfo?.description || '请从智能体市场发起会话' }}</div>
          </div>
        </div>
        <div class="chat-messages">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['bubble', msg.role]"
          >
            <div class="role">{{ msg.role === 'user' ? '你' : '智能体' }}</div>
            <div class="content">{{ msg.content }}</div>
          </div>
          <div v-if="sending" class="bubble assistant">
            <div class="role">智能体</div>
            <div class="content">正在思考...</div>
          </div>
        </div>
        <div class="chat-input">
          <a-textarea
            v-model="input"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            placeholder="输入消息..."
            @keydown.enter.exact.prevent="sendMessage"
          />
          <a-button type="primary" :loading="sending" @click="sendMessage">发送</a-button>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.chat-page {
  height: calc(100vh - 112px);
}

.chat-shell {
  display: flex;
  height: 100%;
  gap: 16px;
}

.chat-sidebar {
  width: 260px;
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  border: 1px solid #e5e6eb;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-title {
  font-weight: 600;
  margin-bottom: 12px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding-right: 4px;
}

.history-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  gap: 12px;
  transition: all 0.2s ease;
}

.history-group-header:hover {
  border-color: #c7d2fe;
  background: #eef2ff;
}

.history-group-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.history-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #4f46e5;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.history-title {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-toggle {
  border-radius: 999px;
  padding: 0 12px;
  color: #4338ca;
  border-color: #c7d2fe;
}

.history-toggle:hover {
  color: #312e81;
  border-color: #a5b4fc;
}

.history-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 8px 12px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover {
  border-color: #c7d2fe;
  background: #f8fafc;
}

.placeholder {
  color: #9ca3af;
  font-size: 13px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e6eb;
}

.agent-header {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e6eb;
  align-items: center;
}

.agent-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #1d4ed8;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 18px;
}

.agent-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-name {
  font-weight: 600;
  font-size: 16px;
}

.agent-desc {
  color: #6b7280;
  font-size: 13px;
}

.chat-messages {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  background: #f3f4f6;
  align-self: flex-start;
}

.bubble.user {
  background: #2563eb;
  color: #fff;
  align-self: flex-end;
}

.bubble.assistant {
  background: #f3f4f6;
  color: #111827;
}

.role {
  font-size: 12px;
  opacity: 0.7;
  margin-bottom: 6px;
}

.chat-input {
  padding: 16px 24px 24px;
  border-top: 1px solid #e5e6eb;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.chat-input :deep(.arco-textarea-wrapper) {
  flex: 1;
}
</style>
