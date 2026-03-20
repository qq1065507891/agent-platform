<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import request from '../utils/request'
import { getAgentDetail } from '../api/agents'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  interrupted?: boolean
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
const sendLock = ref(false)
const chatMessagesRef = ref<HTMLElement | null>(null)
const conversation = ref<Conversation | null>(null)
const agentInfo = ref<AgentInfo | null>(null)
const messages = computed(() => conversation.value?.messages ?? [])
const streamAbortController = ref<AbortController | null>(null)
const enableStreamMetrics = import.meta.env.VITE_ENABLE_STREAM_METRICS === 'true'

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

const scrollToBottom = async () => {
  await nextTick()
  const el = chatMessagesRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

const stopStreaming = () => {
  if (streamAbortController.value) {
    streamAbortController.value.abort()
    streamAbortController.value = null
  }
  sending.value = false
}

const sendMessage = async () => {
  if (sendLock.value || sending.value) return
  sendLock.value = true

  if (!conversation.value?.id) {
    sendLock.value = false
    Message.warning('会话尚未就绪')
    return
  }
  if (!input.value.trim()) {
    sendLock.value = false
    Message.warning('请输入消息')
    return
  }

  sending.value = true
  const content = input.value.trim()
  input.value = ''

  const list = conversation.value.messages
  const activeMessages = list.filter((m) => !m.pending)
  if (activeMessages.length !== list.length) {
    conversation.value.messages = activeMessages
  }

  conversation.value.messages.push({ role: 'user', content })
  const pendingMessage: ChatMessage = { role: 'assistant', content: '正在思考...', pending: true }
  conversation.value.messages.push(pendingMessage)
  await scrollToBottom()

  const controller = new AbortController()
  streamAbortController.value = controller

  try {
    const token = localStorage.getItem('access_token')
    const streamStartedAt = performance.now()
    let firstDeltaAt: number | null = null
    let deltaCount = 0
    let deltaChars = 0
    let transportDelayTotalMs = 0
    let transportDelayCount = 0

    const response = await fetch(`/api/v1/conversations/${conversation.value.id}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content, attachments: [] }),
      signal: controller.signal,
    })

    if (!response.ok || !response.body) {
      throw new Error('流式请求失败')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let fullText = ''

    const setPendingText = async (text: string) => {
      const pendingIndex = conversation.value!.messages.findIndex((m) => m.pending)
      if (pendingIndex >= 0) {
        conversation.value!.messages[pendingIndex] = { role: 'assistant', content: text || '正在思考...', pending: true }
        await scrollToBottom()
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        const line = chunk
          .split('\n')
          .find((item) => item.startsWith('data: '))
        if (!line) continue

        const raw = line.slice(6)
        let payload: any
        try {
          payload = JSON.parse(raw)
        } catch {
          continue
        }

        if (payload.type === 'delta') {
          if (firstDeltaAt === null) {
            firstDeltaAt = performance.now()
          }
          const delta = payload.content || ''
          deltaCount += 1
          deltaChars += delta.length
          const serverTs = Number(payload.server_ts_ms || 0)
          if (serverTs > 0) {
            const delay = Date.now() - serverTs
            if (delay >= 0 && delay < 60_000) {
              transportDelayTotalMs += delay
              transportDelayCount += 1
            }
          }
          fullText += delta
          await setPendingText(fullText)
        }

        if (payload.type === 'done') {
          fullText = payload.assistant_message || fullText
        }
      }
    }

    const reply = fullText.trim() || '已收到你的消息，但当前没有生成文本回复。'
    const pendingIndex = conversation.value.messages.findIndex((m) => m.pending)
    if (pendingIndex >= 0) {
      conversation.value.messages[pendingIndex] = { role: 'assistant', content: reply }
    } else {
      conversation.value.messages.push({ role: 'assistant', content: reply })
    }

    if (enableStreamMetrics) {
      const finishedAt = performance.now()
      const totalSeconds = Math.max((finishedAt - streamStartedAt) / 1000, 0.001)
      const firstTokenLatencyMs = firstDeltaAt === null ? null : Math.max(firstDeltaAt - streamStartedAt, 0)
      const tokenPerSecond = deltaCount / totalSeconds
      const avgTransportDelayMs = transportDelayCount > 0 ? transportDelayTotalMs / transportDelayCount : null
      console.info('[chat-stream-metrics]', {
        conversationId: conversation.value.id,
        agentId: agentId.value,
        firstTokenLatencyMs: firstTokenLatencyMs === null ? null : Math.round(firstTokenLatencyMs),
        avgTransportDelayMs: avgTransportDelayMs === null ? null : Number(avgTransportDelayMs.toFixed(1)),
        deltaCount,
        deltaChars,
        tokenPerSecond: Number(tokenPerSecond.toFixed(2)),
        totalDurationMs: Math.round(finishedAt - streamStartedAt),
      })
    }
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      const pendingIndex = conversation.value.messages.findIndex((m) => m.pending)
      if (pendingIndex >= 0) {
        const current = conversation.value.messages[pendingIndex].content.trim()
        conversation.value.messages[pendingIndex] = {
          role: 'assistant',
          content: current || '已停止生成。',
          interrupted: true,
        }
      }
      Message.info('已停止生成')
    } else {
      const pendingIndex = conversation.value.messages.findIndex((m) => m.pending)
      if (pendingIndex >= 0) {
        conversation.value.messages[pendingIndex] = { role: 'assistant', content: '本次回复失败，请稍后重试。' }
      } else {
        conversation.value.messages.push({ role: 'assistant', content: '本次回复失败，请稍后重试。' })
      }
      Message.error(error?.message || '发送失败')
    }
  } finally {
    streamAbortController.value = null
    sending.value = false
    sendLock.value = false
    await scrollToBottom()
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
        <div ref="chatMessagesRef" class="chat-messages">
          <div v-if="!messages.length" class="empty-state">
            还没有消息，向智能体打个招呼吧。
          </div>
          <div v-for="(msg, idx) in messages" :key="idx" :class="['bubble', msg.role]">
            <div class="role">{{ msg.role === 'user' ? '你' : '智能体' }}</div>
            <div class="content">
              {{ msg.content }}
              <span v-if="msg.pending" class="typing-cursor" aria-hidden="true"></span>
              <span v-if="msg.interrupted && !msg.pending" class="interrupted-tag">（已中断）</span>
            </div>
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
          <a-button v-if="sending" status="danger" @click="stopStreaming">停止生成</a-button>
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

.typing-cursor {
  display: inline-block;
  width: 8px;
  height: 1em;
  margin-left: 3px;
  vertical-align: text-bottom;
  background: currentColor;
  animation: blink 1s steps(1, end) infinite;
  opacity: 0.85;
}

.interrupted-tag {
  margin-left: 6px;
  font-size: 12px;
  color: #9ca3af;
}

@keyframes blink {
  0%,
  49% {
    opacity: 0.85;
  }
  50%,
  100% {
    opacity: 0;
  }
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
