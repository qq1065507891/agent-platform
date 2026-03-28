<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { getAgentDetail } from '../api/agents'
import {
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
} from '../api/conversations'
import { getApiErrorMessage } from '../utils/request'

interface MessageSource {
  doc_id?: string
  source?: string
  version?: number | string
  chunk_index?: number | string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  interrupted?: boolean
  sources?: MessageSource[]
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

const toTimestamp = (value?: string) => {
  if (!value) return 0
  const ts = new Date(value).getTime()
  return Number.isFinite(ts) ? ts : 0
}

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

  const groups = Object.values(map).map((group) => ({
    ...group,
    items: [...group.items].sort((a, b) => toTimestamp(b.created_at) - toTimestamp(a.created_at)),
  }))

  groups.sort((a, b) => {
    const aLatest = a.items.length ? toTimestamp(a.items[0].created_at) : 0
    const bLatest = b.items.length ? toTimestamp(b.items[0].created_at) : 0
    return bLatest - aLatest
  })

  return groups
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
    const data = await getConversation(conversationId.value)
    conversation.value = data
    if (data?.agent_id) {
      agentInfo.value = await getAgentDetail(data.agent_id)
    }
  } catch (error: any) {
    Message.error(getApiErrorMessage(error, '加载会话失败'))
  } finally {
    loading.value = false
  }
}

const fetchHistoryList = async () => {
  try {
    const data = await listConversations()
    historyList.value = Array.isArray(data) ? data : []
  } catch (error: any) {
    Message.error(getApiErrorMessage(error, '加载历史对话失败'))
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
  event.stopPropagation()
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
  if (!item?.id) return

  Modal.confirm({
    title: '确认删除该会话？',
    content: `删除后不可恢复：${item.title || `会话 ${item.id.slice(0, 6)}`}`,
    okButtonProps: { status: 'danger', loading: deletingConversationId.value === item.id },
    onOk: async () => {
      if (deletingConversationId.value) return
      deletingConversationId.value = item.id
      hideContextMenu()
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
    onCancel: () => {
      hideContextMenu()
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
    let doneSources: MessageSource[] = []
    let streamDone = false
    const streamIdleTimeoutMs = 3000
    let streamIdleTimer: ReturnType<typeof setTimeout> | null = null

    const scheduleStreamIdleGuard = () => {
      if (streamIdleTimer) {
        clearTimeout(streamIdleTimer)
      }
      streamIdleTimer = setTimeout(async () => {
        if (streamDone || !fullText.trim()) return
        console.warn('[chat-stream] idle timeout reached, force finishing stream')
        streamDone = true
        try {
          await reader.cancel()
        } catch {
          // ignore cancel race
        }
      }, streamIdleTimeoutMs)
    }

    const clearStreamIdleGuard = () => {
      if (streamIdleTimer) {
        clearTimeout(streamIdleTimer)
        streamIdleTimer = null
      }
    }

    const setPendingText = async (text: string) => {
      const pendingIndex = conversation.value!.messages.findIndex((m) => m.pending)
      if (pendingIndex >= 0) {
        conversation.value!.messages[pendingIndex] = { role: 'assistant', content: text || '正在思考...', pending: true }
        await scrollToBottom()
      }
    }

    scheduleStreamIdleGuard()

    while (true) {
      if (streamDone) break
      const { done, value } = await reader.read()
      if (done) break
      scheduleStreamIdleGuard()

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        if (streamDone) break
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

        if (payload.type === 'done' || payload.type === 'final') {
          fullText = payload.assistant_message || payload.content || fullText
          doneSources = Array.isArray(payload.sources) ? payload.sources : []
          streamDone = true
          clearStreamIdleGuard()
          try {
            await reader.cancel()
          } catch {
            // ignore cancel race
          }
          break
        }
      }
    }

    clearStreamIdleGuard()

    if (!streamDone) {
      console.warn('[chat-stream] stream ended without explicit done/final event')
    }

    const finalReply = fullText.trim() || '已收到你的消息，但当前没有生成文本回复。'
    const pendingIndex = conversation.value.messages.findIndex((m) => m.pending)
    if (pendingIndex >= 0) {
      conversation.value.messages[pendingIndex] = { role: 'assistant', content: finalReply, sources: doneSources }
    } else {
      conversation.value.messages.push({ role: 'assistant', content: finalReply, sources: doneSources })
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
      Message.error(getApiErrorMessage(error, '发送失败'))
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

              <details v-if="msg.role === 'assistant' && msg.sources && msg.sources.length" class="sources-panel">
                <summary>引用来源（{{ msg.sources.length }}）</summary>
                <ul class="sources-list">
                  <li v-for="(src, sidx) in msg.sources" :key="`${src.doc_id || 'doc'}-${src.chunk_index || sidx}-${sidx}`">
                    <div class="source-line">
                      <strong>{{ src.source || '未命名文档' }}</strong>
                      <span v-if="src.version !== undefined" class="source-meta">v{{ src.version }}</span>
                      <span v-if="src.chunk_index !== undefined" class="source-meta">#{{ src.chunk_index }}</span>
                    </div>
                    <div v-if="src.doc_id" class="source-id">{{ src.doc_id }}</div>
                  </li>
                </ul>
              </details>
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
      @contextmenu.prevent.stop
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
  min-width: 130px;
  background: rgba(18, 28, 56, 0.95);
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  box-shadow: var(--shadow-lg);
  padding: 6px;
}

.context-menu-item {
  width: 100%;
  justify-content: flex-start;
}

.chat-sidebar,
.chat-main {
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
}

.chat-sidebar {
  background: rgba(30, 45, 86, 0.68);
}

.chat-main {
  background: rgba(74, 101, 170, 0.26);
}

.chat-sidebar {
  width: 300px;
  border-radius: var(--radius-xl);
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-title {
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text-1);
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
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
  gap: 12px;
  transition: all 0.2s ease;
}

.history-group-header:hover {
  border-color: rgba(109, 94, 248, 0.8);
  background: rgba(109, 94, 248, 0.22);
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
  background: linear-gradient(135deg, var(--brand-1), var(--brand-2));
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
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-toggle {
  border-radius: 999px;
  padding: 0 12px;
}

.history-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover {
  border-color: rgba(109, 94, 248, 0.85);
  background: rgba(109, 94, 248, 0.24);
  transform: translateY(-1px);
}

.placeholder {
  color: var(--text-3);
  font-size: 13px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-xl);
}

.agent-header {
  display: flex;
  gap: 12px;
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  align-items: center;
  background: linear-gradient(135deg, rgba(109, 94, 248, 0.25), rgba(39, 211, 195, 0.1));
}

.agent-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--brand-1), var(--brand-2));
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
  font-weight: 700;
  font-size: 16px;
  color: var(--text-1);
}

.agent-desc {
  color: #e4ebff;
  font-size: 13px;
}

.chat-messages {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  overflow-y: auto;
}

.bubble {
  max-width: 74%;
  padding: 13px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  align-self: flex-start;
  color: #f3f6ff;
}

.bubble.user {
  background: linear-gradient(135deg, rgba(109, 94, 248, 0.9), rgba(79, 140, 255, 0.9));
  color: #fff;
  align-self: flex-end;
  border-color: transparent;
}

.bubble.assistant {
  background: rgba(255, 255, 255, 0.07);
  color: var(--text-1);
}

.role {
  font-size: 12px;
  opacity: 0.86;
  margin-bottom: 7px;
}

.content {
  line-height: 1.68;
  letter-spacing: 0.1px;
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
  color: var(--text-3);
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
  padding: 16px 24px 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: rgba(255, 255, 255, 0.03);
  box-shadow: inset 0 8px 28px rgba(109, 94, 248, 0.08);
}

.chat-input :deep(.arco-textarea-wrapper) {
  flex: 1;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.chat-input :deep(.arco-textarea-wrapper:hover),
.chat-input :deep(.arco-textarea-wrapper.arco-textarea-focus) {
  border-color: rgba(109, 94, 248, 0.75) !important;
  box-shadow: 0 0 0 3px rgba(109, 94, 248, 0.18);
}

.chat-input :deep(.arco-btn-primary) {
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
  background: linear-gradient(135deg, #7967ff, #52a7ff) !important;
  box-shadow: 0 14px 30px rgba(82, 167, 255, 0.42);
}

.chat-input :deep(.arco-btn-primary:hover) {
  transform: translateY(-1px);
  filter: brightness(1.08);
  box-shadow: 0 18px 34px rgba(82, 167, 255, 0.5);
}

.sources-panel {
  margin-top: 10px;
  border: 1px solid rgba(39, 211, 195, 0.35);
  background: rgba(39, 211, 195, 0.08);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
}

.sources-panel summary {
  cursor: pointer;
  color: #7ae9de;
  font-weight: 600;
  outline: none;
}

.sources-list {
  margin: 8px 0 0;
  padding-left: 18px;
}

.source-line {
  display: flex;
  gap: 8px;
  align-items: center;
  color: var(--text-2);
}

.source-meta {
  color: var(--text-3);
}

.source-id {
  color: var(--text-3);
  font-size: 11px;
  margin-top: 2px;
  word-break: break-all;
}
</style>
