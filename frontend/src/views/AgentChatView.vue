<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import request from '../utils/request'
import { getAgentDetail } from '../api/agents'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Conversation {
  id: string
  agent_id: string
  messages: ChatMessage[]
}

interface AgentInfo {
  id: string
  name: string
  description?: string
}

const route = useRoute()
const agentId = computed(() => String(route.params.agentId || ''))
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const conversation = ref<Conversation | null>(null)
const agentInfo = ref<AgentInfo | null>(null)
const messages = computed(() => conversation.value?.messages ?? [])

const fetchAgentInfo = async () => {
  if (!agentId.value) return
  try {
    agentInfo.value = await getAgentDetail(agentId.value)
  } catch (error: any) {
    Message.error(error?.message || '加载智能体失败')
  }
}

const ensureConversation = async () => {
  if (!agentId.value) return
  if (conversation.value?.id) return
  loading.value = true
  try {
    const data = await request.post('/conversations', { agent_id: agentId.value })
    conversation.value = data
  } catch (error: any) {
    Message.error(error?.message || '创建会话失败')
  } finally {
    loading.value = false
  }
}

const fetchConversation = async () => {
  if (!conversation.value?.id) return
  loading.value = true
  try {
    const data = await request.get(`/conversations/${conversation.value.id}`)
    conversation.value = data
  } catch (error: any) {
    Message.error(error?.message || '加载会话失败')
  } finally {
    loading.value = false
  }
}

const sendMessage = async () => {
  if (!conversation.value?.id) {
    Message.warning('会话尚未就绪')
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
    const data = await request.post(`/conversations/${conversation.value.id}/messages`, {
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

const init = async () => {
  await fetchAgentInfo()
  await ensureConversation()
  await fetchConversation()
}

onMounted(init)

watch(
  () => agentId.value,
  () => {
    conversation.value = null
    init()
  }
)
</script>

<template>
  <div class="agent-chat-page">
    <a-spin :loading="loading" class="agent-chat-shell">
      <div class="agent-panel">
        <div class="agent-banner">
          <div class="agent-avatar">{{ agentInfo?.name?.charAt(0) || 'A' }}</div>
          <div class="agent-title">{{ agentInfo?.name || '智能体' }}</div>
          <div class="agent-desc">{{ agentInfo?.description || '暂无描述' }}</div>
        </div>
        <div class="agent-hint">欢迎与你的智能体对话，输入问题即可开始。</div>
      </div>

      <div class="chat-panel">
        <div class="chat-messages">
          <div v-if="!messages.length" class="empty-state">
            还没有消息，向智能体打个招呼吧。
          </div>
          <div v-for="(msg, idx) in messages" :key="idx" :class="['bubble', msg.role]">
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
.agent-chat-page {
  height: calc(100vh - 112px);
}

.agent-chat-shell {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  height: 100%;
}

.agent-panel {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  border: 1px solid #e5e6eb;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agent-banner {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 12px;
  padding: 16px 12px;
  border-radius: 12px;
  background: linear-gradient(180deg, #eef2ff 0%, #ffffff 100%);
}

.agent-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 600;
}

.agent-title {
  font-size: 18px;
  font-weight: 600;
}

.agent-desc {
  color: #6b7280;
  font-size: 13px;
}

.agent-hint {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.6;
}

.chat-panel {
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e5e6eb;
  display: flex;
  flex-direction: column;
}

.chat-messages {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.empty-state {
  color: #9ca3af;
  font-size: 13px;
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
