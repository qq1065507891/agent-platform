<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import request from '../utils/request'
import {
  deleteConversation,
  getAgentDetail,
  listUserConversations,
  renameConversation,
} from '../api/agents'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  interrupted?: boolean
}

interface Conversation {
  id: string
  agent_id: string
  title?: string
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
const chatMessagesRef = ref<HTMLElement | null>(null)
const streamAbortController = ref<AbortController | null>(null)
const enableStreamMetrics = import.meta.env.VITE_ENABLE_STREAM_METRICS === 'true'
const TRACE_KEY = 'x_request_id'

const getRequestId = () => {
  const existing = sessionStorage.getItem(TRACE_KEY)
  if (existing) return existing
  const created = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  sessionStorage.setItem(TRACE_KEY, created)
  return created
}
const deletingConversationId = ref('')
const renamingConversationId = ref('')
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  item: null as Conversation | null,
})

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
  hideContextMenu()
  router.push(`/chat/${item.id}`)
}

const hideContextMenu = () => {
  contextMenu.value.visible = false
  contextMenu.value.item = null
}

const onConversationContextMenu = (event: MouseEvent, item: Conversation) => {
  event.preventDefault()
  const menuWidth = 140
  const menuHeight = 44
  const padding = 8
  const maxX = window.innerWidth - menuWidth - padding
  const maxY = window.innerHeight - menuHeight - padding
  contextMenu.value = {
    visible: true,
    x: Math.min(event.clientX, maxX),
    y: Math.min(event.clientY, maxY),
    item,
  }
}

const onCopyConversationId = async () => {
  const item = contextMenu.value.item
  hideContextMenu()
  if (!item?.id) return
  try {
    await navigator.clipboard.writeText(item.id)
    Message.success('会话 ID 已复制')
  } catch {
    Message.error('复制失败，请手动复制')
  }
}

const onRenameConversation = () => {
  const item = contextMenu.value.item
  hideContextMenu()
  if (!item?.id) return

  let titleValue = item.title || ''
  Modal.confirm({
    title: '重命名会话',
    content: () =>
      h('div', { style: 'display:flex;flex-direction:column;gap:8px;' }, [
        h('span', '请输入新的会话标题'),
        h('input', {
          value: titleValue,
          maxlength: 120,
          placeholder: '例如：面试题整理',
          style:
            'width:100%;padding:8px 10px;border:1px solid #dcdfe6;border-radius:6px;outline:none;',
          onInput: (e: Event) => {
            const target = e.target as HTMLInputElement
            titleValue = target.value
          },
        }),
      ]),
    onOk: async () => {
      const nextTitle = titleValue.trim()
      if (!nextTitle) {
        Message.warning('标题不能为空')
        throw new Error('标题不能为空')
      }
      if (renamingConversationId.value) return
      renamingConversationId.value = item.id
      try {
        await renameConversation(item.id, { title: nextTitle })
        Message.success('会话已重命名')
        await fetchHistoryList()
      } catch (error: any) {
        const detail = error?.response?.data?.detail
        Message.error(detail || error?.message || '重命名失败')
        throw error
      } finally {
        renamingConversationId.value = ''
      }
    },
  })
}

const onDeleteConversation = () => {
  const item = contextMenu.value.item
  hideContextMenu()
  if (!item?.id) return

  Modal.confirm({
    title: '确认删除该会话？',
    content: `删除后不可恢复：${item.title || `会话 ${item.id.slice(0, 6)}`}`,
    okButtonProps: { status: 'danger', loading: deletingConversationId.value === item.id },
    onOk: async () => {
      if (deletingConversationId.value) return
      deletingConversationId.value = item.id
      try {
        await deleteConversation(item.id)
        Message.success('会话已删除')
        if (conversationId.value === item.id) {
          conversation.value = null
          agentInfo.value = null
          router.push('/chat/placeholder')
        }
        await fetchHistoryList()
      } catch (error: any) {
        const detail = error?.response?.data?.detail
        Message.error(detail || error?.message || '删除会话失败')
      } finally {
        deletingConversationId.value = ''
      }
    },
  })
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
  if (sending.value) return
  if (!conversationId.value || conversationId.value === 'placeholder') {
    Message.warning('请先在智能体市场创建会话')
    return
  }
  if (!input.value.trim()) {
    Message.warning('请输入消息')
    return
  }
  if (!conversation.value) {
    Message.warning('会话未加载完成，请稍后重试')
    return
  }

  const activeMessages = conversation.value.messages.filter((m) => !m.pending)
  if (activeMessages.length !== conversation.value.messages.length) {
    conversation.value.messages = activeMessages
  }

  sending.value = true
  const content = input.value.trim()
  input.value = ''
  conversation.value.messages.push({ role: 'user', content })
  const pendingMessage: ChatMessage = { role: 'assistant', content: '正在思考...', pending: true }
  conversation.value.messages.push(pendingMessage)
  await scrollToBottom()

  const controller = new AbortController()
  streamAbortController.value = controller

  try {
    const token = localStorage.getItem('access_token')
    const requestId = getRequestId()
    const streamStartedAt = performance.now()
    let firstDeltaAt: number | null = null
    let deltaCount = 0
    let deltaChars = 0
    let transportDelayTotalMs = 0
    let transportDelayCount = 0

    const response = await fetch(`/api/v1/conversations/${conversationId.value}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': requestId,
        'X-Trace-Id': requestId,
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

    const finalReply = fullText.trim() || '已收到你的消息，但当前没有生成文本回复。'
    const pendingIndex = conversation.value.messages.findIndex((m) => m.pending)
    if (pendingIndex >= 0) {
      conversation.value.messages[pendingIndex] = { role: 'assistant', content: finalReply }
    } else {
      conversation.value.messages.push({ role: 'assistant', content: finalReply })
    }

    if (enableStreamMetrics) {
      const finishedAt = performance.now()
      const totalSeconds = Math.max((finishedAt - streamStartedAt) / 1000, 0.001)
      const firstTokenLatencyMs = firstDeltaAt === null ? null : Math.max(firstDeltaAt - streamStartedAt, 0)
      const tokenPerSecond = deltaCount / totalSeconds
      const avgTransportDelayMs = transportDelayCount > 0 ? transportDelayTotalMs / transportDelayCount : null
      console.info('[chat-stream-metrics]', {
        conversationId: conversationId.value,
        agentId: conversation.value.agent_id,
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
        conversation.value.messages[pendingIndex] = {
          role: 'assistant',
          content: '本次回复失败，请稍后重试。',
        }
      } else {
        conversation.value.messages.push({ role: 'assistant', content: '本次回复失败，请稍后重试。' })
      }
      Message.error(error?.message || '发送失败')
    }
  } finally {
    streamAbortController.value = null
    sending.value = false
    await scrollToBottom()
    fetchHistoryList()
  }
}

onMounted(() => {
  fetchConversation()
  fetchHistoryList()
  window.addEventListener('click', hideContextMenu)
  window.addEventListener('contextmenu', hideContextMenu)
})

onUnmounted(() => {
  window.removeEventListener('click', hideContextMenu)
  window.removeEventListener('contextmenu', hideContextMenu)
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
                @contextmenu="onConversationContextMenu($event, item)"
              >
                <div class="history-title">{{ item.title || `会话 ${item.id.slice(0, 6)}` }}</div>
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
        <div ref="chatMessagesRef" class="chat-messages">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['bubble', msg.role]"
          >
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

    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @click.stop
    >
      <a-button
        type="text"
        size="mini"
        class="context-menu-item"
        :disabled="!!deletingConversationId || !!renamingConversationId"
        @click="onCopyConversationId"
      >
        复制会话 ID
      </a-button>
      <a-button
        type="text"
        size="mini"
        class="context-menu-item"
        :loading="renamingConversationId === contextMenu.item?.id"
        :disabled="!!deletingConversationId"
        @click="onRenameConversation"
      >
        重命名会话
      </a-button>
      <a-button
        type="text"
        status="danger"
        size="mini"
        class="context-menu-item"
        :loading="deletingConversationId === contextMenu.item?.id"
        :disabled="!!renamingConversationId"
        @click="onDeleteConversation"
      >
        删除会话
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  height: calc(100vh - 112px);
  position: relative;
}

.chat-shell {
  display: flex;
  height: 100%;
  gap: 16px;
}

.context-menu {
  position: fixed;
  z-index: 2000;
  min-width: 120px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
  padding: 6px;
}

.context-menu-item {
  width: 100%;
  justify-content: flex-start;
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
