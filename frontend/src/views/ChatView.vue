<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import request from '../utils/request'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Conversation {
  id: string
  agent_id: string
  messages: ChatMessage[]
}

const route = useRoute()
const conversationId = computed(() => String(route.params.id || ''))
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const conversation = ref<Conversation | null>(null)
const messages = computed(() => conversation.value?.messages ?? [])

const fetchConversation = async () => {
  if (!conversationId.value || conversationId.value === 'placeholder') return
  loading.value = true
  try {
    const data = await request.get(`/conversations/${conversationId.value}`)
    conversation.value = data
  } catch (error: any) {
    Message.error(error?.message || '加载会话失败')
  } finally {
    loading.value = false
  }
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

onMounted(fetchConversation)
</script>

<template>
  <div class="chat-page">
    <a-spin :loading="loading" class="chat-shell">
      <div class="chat-sidebar">
        <div class="sidebar-title">历史对话</div>
        <div class="placeholder">当前仅展示所选会话</div>
      </div>

      <div class="chat-main">
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
          <a-textarea v-model="input" :auto-size="{ minRows: 3, maxRows: 6 }" placeholder="输入消息..." />
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
  width: 240px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #e5e6eb;
}

.sidebar-title {
  font-weight: 600;
  margin-bottom: 12px;
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
