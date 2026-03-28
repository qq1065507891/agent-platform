<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { createAgent, updateAgent } from '../../api/agents'
import {
  batchDeleteKnowledgeDocuments,
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  getKnowledgeTaskStatus,
  purgeDeletedKnowledgeDocuments,
  uploadKnowledge,
  type BatchDeleteKnowledgeResponse,
  type KnowledgeDocumentItem,
  type KnowledgeTaskStatusResponse,
  type KnowledgeUploadResponse,
} from '../../api/knowledge'
import { getSkills, type SkillItem } from '../../api/skills'

interface AgentBinding {
  skill_id: string
  type?: string
}

interface AgentEditable {
  id: string
  name: string
  description?: string
  prompt_template: string
  is_public?: boolean
  skills?: AgentBinding[]
}

const props = defineProps<{ mode?: 'create' | 'edit'; agent?: AgentEditable | null }>()
const emit = defineEmits<{
  (e: 'saved', payload: { id: string; mode: 'create' | 'edit' }): void
  (e: 'cancel'): void
}>()

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const skillsLoading = ref(false)
const skillOptions = ref<SkillItem[]>([])
const isDirty = ref(false)

const form = reactive({
  name: '',
  description: '',
  prompt_template: '',
  is_public: false,
  skills: [] as string[],
  mcpTools: [] as string[],
  knowledgeFiles: [] as File[],
})

const uploadFileList = ref<any[]>([])
const uploading = ref(false)
const uploadResults = ref<KnowledgeUploadResponse[]>([])
const uploadDetailExpanded = ref(false)
const documentsLoading = ref(false)
const documents = ref<KnowledgeDocumentItem[]>([])
const deletingDocId = ref('')
const selectedDocumentIds = ref<string[]>([])
const batchDeleting = ref(false)
const purgeTaskId = ref('')
const purgeTaskState = ref('')
const purgeTaskMessage = ref('')
const purgePolling = ref(false)
const purgeIntervalId = ref<ReturnType<typeof setInterval> | null>(null)
const docKeyword = ref('')
const onlyShowDeleted = ref(false)

const currentMode = computed(() => props.mode || 'create')
const isEditMode = computed(() => currentMode.value === 'edit')

const markDirty = () => {
  isDirty.value = true
}

const markClean = () => {
  isDirty.value = false
}

const uploadSummary = computed(() => {
  const docCount = uploadResults.value.length
  const chunkCount = uploadResults.value.reduce((total, item) => total + Number(item.chunk_count || 0), 0)
  return { docCount, chunkCount }
})

const allDocumentsChecked = computed(
  () => documents.value.length > 0 && selectedDocumentIds.value.length === documents.value.length
)

const deletedDocumentsCount = computed(() =>
  documents.value.filter((item) => String(item.status || '').toLowerCase() === 'deleted').length
)

const filteredDocuments = computed(() => {
  const keyword = docKeyword.value.trim().toLowerCase()
  return documents.value.filter((doc) => {
    if (onlyShowDeleted.value && String(doc.status || '').toLowerCase() !== 'deleted') {
      return false
    }
    if (!keyword) return true
    const source = String(doc.source || '').toLowerCase()
    const id = String(doc.doc_id || '').toLowerCase()
    return source.includes(keyword) || id.includes(keyword)
  })
})

const filteredCountLabel = computed(() => {
  const total = documents.value.length
  const filtered = filteredDocuments.value.length
  if (!docKeyword.value.trim() && !onlyShowDeleted.value) return `共 ${total} 条`
  return `筛选结果 ${filtered} / ${total}`
})

const rules = {
  name: [{ required: true, message: '请输入名称' }],
  prompt_template: [{ required: true, message: '请输入提示词' }],
}

const selectableSkillIds = computed(
  () => new Set(skillOptions.value.filter((item) => item.status === 'active').map((item) => item.skill_id))
)

const skillSelectOptions = computed(() => {
  return skillOptions.value
    .filter((item) => item && typeof item.skill_id === 'string' && typeof item.name === 'string' && item.source_type !== 'mcp')
    .map((item) => {
      const active = item.status === 'active'
      return {
        label: active
          ? `【可用】${item.name}`
          : `【不可用】${item.name}（${getUnavailableSkillStatusLabel(item)}）`,
        value: item.skill_id,
        disabled: !active,
      }
    })
    .sort((a, b) => {
      if (a.disabled !== b.disabled) return a.disabled ? 1 : -1
      return a.label.localeCompare(b.label, 'zh-CN')
    })
})

const mcpSelectOptions = computed(() => {
  return skillOptions.value
    .filter((item) => item && typeof item.skill_id === 'string' && typeof item.name === 'string' && item.source_type === 'mcp')
    .map((item) => {
      const active = item.status === 'active'
      return {
        label: active
          ? `【可用】${item.name}`
          : `【不可用】${item.name}（${getUnavailableSkillStatusLabel(item)}）`,
        value: item.skill_id,
        disabled: !active,
      }
    })
    .sort((a, b) => {
      if (a.disabled !== b.disabled) return a.disabled ? 1 : -1
      return a.label.localeCompare(b.label, 'zh-CN')
    })
})

const getUnavailableSkillStatusLabel = (item: SkillItem) => {
  if (item.status === 'active') return '可用'
  if (item.source_type !== 'builtin' && !item.current_revision_id) return '加载中'
  if (item.source_type !== 'builtin' && item.current_revision_id) return '审核失败/已禁用'
  return '已禁用'
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const highlightText = (value: string) => {
  const safe = escapeHtml(value)
  const keyword = docKeyword.value.trim()
  if (!keyword) return safe
  const pattern = new RegExp(escapeRegExp(keyword), 'ig')
  return safe.replace(pattern, (match) => `<mark class="keyword-hit">${match}</mark>`)
}

const fetchSkills = async () => {
  skillsLoading.value = true
  try {
    const pageSize = 100
    let page = 1
    let total = 0
    const all: SkillItem[] = []

    do {
      const data = await getSkills({ page, page_size: pageSize, status: 'active' })
      const list = Array.isArray(data?.list)
        ? data.list.filter((item: SkillItem) => item && typeof item.skill_id === 'string')
        : []
      total = Number(data?.total || 0)
      all.push(...list)
      page += 1
    } while ((page - 1) * pageSize < total && page <= 20)

    skillOptions.value = all
    form.skills = form.skills.filter((id) => selectableSkillIds.value.has(id))
    form.mcpTools = form.mcpTools.filter((id) => selectableSkillIds.value.has(id))
  } catch (error: any) {
    Message.error(error?.message || '获取技能失败')
  } finally {
    skillsLoading.value = false
  }
}

const goMcpManagement = () => {
  router.push('/admin/mcp-tools')
}

const onFileChange = (fileList: any[] | undefined) => {
  if (!fileList?.length) {
    form.knowledgeFiles = []
    return
  }
  form.knowledgeFiles = fileList
    .map((item: any) => item.file as File | undefined)
    .filter((file: File | undefined): file is File => Boolean(file))
}

const fillFormFromAgent = (agent: AgentEditable) => {
  form.name = agent.name || ''
  form.description = agent.description || ''
  form.prompt_template = agent.prompt_template || ''
  form.is_public = Boolean(agent.is_public)

  const bindings = Array.isArray(agent.skills) ? agent.skills : []
  form.skills = bindings
    .filter((item) => item && item.skill_id && (item.type || 'skill') !== 'mcp')
    .map((item) => item.skill_id)
  form.mcpTools = bindings
    .filter((item) => item && item.skill_id && (item.type || 'skill') === 'mcp')
    .map((item) => item.skill_id)
}

const fetchKnowledgeDocuments = async (agentId: string) => {
  if (!agentId) return
  documentsLoading.value = true
  try {
    const data = await getKnowledgeDocuments({ agent_id: agentId, page: 1, page_size: 100 })
    documents.value = Array.isArray(data?.list) ? data.list : []
    selectedDocumentIds.value = selectedDocumentIds.value.filter((id) =>
      documents.value.some((item) => item.doc_id === id)
    )
  } catch (error: any) {
    Message.error(error?.message || '获取知识库文档失败')
  } finally {
    documentsLoading.value = false
  }
}

const onDeleteDocument = (doc: KnowledgeDocumentItem) => {
  if (!props.agent?.id || deletingDocId.value || batchDeleting.value) return
  Modal.confirm({
    title: '确认删除该知识文档？',
    content: `删除后不可恢复：${doc.source || doc.doc_id}`,
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      if (!props.agent?.id) return
      deletingDocId.value = doc.doc_id
      try {
        await deleteKnowledgeDocument(doc.doc_id, props.agent.id, 'soft')
        Message.success('文档已删除')
        await fetchKnowledgeDocuments(props.agent.id)
      } catch (error: any) {
        Message.error(error?.message || '删除文档失败')
      } finally {
        deletingDocId.value = ''
      }
    },
  })
}

const onBatchDeleteDocuments = (docIds?: string[]) => {
  const ids = docIds?.length ? [...docIds] : [...selectedDocumentIds.value]
  if (!props.agent?.id || !ids.length || batchDeleting.value || deletingDocId.value) return
  Modal.confirm({
    title: '确认批量删除知识文档？',
    content: `本次将删除 ${ids.length} 个文档，删除后不可恢复。`,
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      if (!props.agent?.id) return
      batchDeleting.value = true
      try {
        const resp = (await batchDeleteKnowledgeDocuments({
          agent_id: props.agent.id,
          doc_ids: ids,
          delete_mode: 'soft',
        })) as BatchDeleteKnowledgeResponse

        const successCount = Number(resp?.success_count || 0)
        const results = Array.isArray(resp?.results) ? resp.results : []
        const failed = results.filter((item) => !item.deleted)

        if (failed.length > 0) {
          const failedIds = failed.map((item) => item.doc_id).slice(0, 5).join('，')
          Message.warning(
            `批量删除完成：成功 ${successCount} / ${ids.length}，失败 ${failed.length}` +
              (failedIds ? `（失败示例：${failedIds}${failed.length > 5 ? '...' : ''}）` : '')
          )
        } else {
          Message.success(`批量删除完成：成功 ${successCount} / ${ids.length}`)
        }

        selectedDocumentIds.value = []
        await fetchKnowledgeDocuments(props.agent.id)
      } catch (error: any) {
        Message.error(error?.message || '批量删除失败')
      } finally {
        batchDeleting.value = false
      }
    },
  })
}

const clearPurgePolling = () => {
  if (purgeIntervalId.value) {
    clearInterval(purgeIntervalId.value)
    purgeIntervalId.value = null
  }
  purgePolling.value = false
}

const pollPurgeTaskStatus = (taskId: string) => {
  clearPurgePolling()
  purgePolling.value = true
  purgeTaskId.value = taskId
  purgeTaskState.value = 'PENDING'
  purgeTaskMessage.value = '清理任务已提交，正在执行...'

  const runOnce = async () => {
    try {
      const resp = (await getKnowledgeTaskStatus(taskId)) as KnowledgeTaskStatusResponse
      const state = String(resp?.state || 'PENDING')
      purgeTaskState.value = state

      if (state === 'SUCCESS') {
        const deletedCount = Number(resp?.result?.deleted_count || 0)
        purgeTaskMessage.value = `清理完成：已硬删除 ${deletedCount} 个片段`
        clearPurgePolling()
        if (props.agent?.id) {
          await fetchKnowledgeDocuments(props.agent.id)
        }
        return
      }

      if (state === 'FAILURE') {
        purgeTaskMessage.value = `清理失败：${resp?.error || '未知错误'}`
        clearPurgePolling()
        return
      }

      purgeTaskMessage.value = `清理中（${state}）...`
    } catch (error: any) {
      purgeTaskMessage.value = `清理状态查询失败：${error?.message || '未知错误'}`
      clearPurgePolling()
    }
  }

  runOnce()
  purgeIntervalId.value = setInterval(runOnce, 2000)
}

const onPurgeDeletedDocuments = async () => {
  if (!props.agent?.id || purgePolling.value) return
  try {
    const resp = (await purgeDeletedKnowledgeDocuments({ agent_id: props.agent.id })) as {
      task_id?: string
      status?: string
    }
    const taskId = String(resp?.task_id || '')
    if (!taskId) {
      Message.error('未获取到清理任务ID')
      return
    }
    Message.success('已提交清理任务')
    pollPurgeTaskStatus(taskId)
  } catch (error: any) {
    Message.error(error?.message || '提交清理任务失败')
  }
}

const onGlobalKeydown = (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    onSubmit()
  }
}

const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const mergedSkillBindings = [
      ...form.skills.map((skillId) => ({ skill_id: skillId, type: 'skill' })),
      ...form.mcpTools.map((skillId) => ({ skill_id: skillId, type: 'mcp' })),
    ]

    let targetAgentId = ''

    if (isEditMode.value && props.agent?.id) {
      await updateAgent(props.agent.id, {
        name: form.name,
        description: form.description || undefined,
        prompt_template: form.prompt_template,
        is_public: form.is_public,
        skills: mergedSkillBindings,
      })
      targetAgentId = props.agent.id
    } else {
      const agent = await createAgent({
        name: form.name,
        description: form.description || undefined,
        prompt_template: form.prompt_template,
        is_public: form.is_public,
        skills: mergedSkillBindings,
      })
      targetAgentId = agent.id
    }

    if (form.knowledgeFiles.length && targetAgentId) {
      uploading.value = true
      const results = [] as KnowledgeUploadResponse[]
      for (const file of form.knowledgeFiles) {
        const result = await uploadKnowledge(file, targetAgentId)
        results.push(result)
      }
      uploadResults.value = results
      uploadDetailExpanded.value = false
      Message.success('知识库上传完成')
    }

    if (isEditMode.value && targetAgentId) {
      await fetchKnowledgeDocuments(targetAgentId)
      Message.success('智能体更新成功')
      emit('saved', { id: targetAgentId, mode: 'edit' })
    } else {
      Message.success('智能体创建成功')
      emit('saved', { id: targetAgentId, mode: 'create' })
    }
    markClean()
  } catch (error: any) {
    Message.error(error?.message || (isEditMode.value ? '更新失败' : '创建失败'))
  } finally {
    uploading.value = false
    loading.value = false
  }
}

watch(
  () => props.agent,
  async (agent) => {
    if (isEditMode.value && agent) {
      fillFormFromAgent(agent)
      await fetchKnowledgeDocuments(agent.id)
      markClean()
      return
    }
    if (!isEditMode.value) {
      documents.value = []
      selectedDocumentIds.value = []
      form.name = ''
      form.description = ''
      form.prompt_template = ''
      form.is_public = false
      form.skills = []
      form.mcpTools = []
      form.knowledgeFiles = []
      uploadFileList.value = []
      uploadResults.value = []
      uploadDetailExpanded.value = false
      purgeTaskState.value = ''
      purgeTaskMessage.value = ''
      purgeTaskId.value = ''
      clearPurgePolling()
      markClean()
    }
  },
  { immediate: true, deep: true }
)

watch(
  () => [
    form.name,
    form.description,
    form.prompt_template,
    form.is_public,
    JSON.stringify(form.skills),
    JSON.stringify(form.mcpTools),
    form.knowledgeFiles.length,
  ],
  () => {
    markDirty()
  }
)

defineExpose({
  isDirty,
  markClean,
})

onMounted(() => {
  fetchSkills()
  window.addEventListener('keydown', onGlobalKeydown)
})
onBeforeUnmount(() => {
  clearPurgePolling()
  window.removeEventListener('keydown', onGlobalKeydown)
})
</script>

<template>
  <div class="agent-form-panel glass-panel">
    <div class="panel-head">
      <div class="panel-head-title">{{ isEditMode ? '编辑配置' : '创建配置' }}</div>
      <a-space size="mini">
        <a-tag bordered color="arcoblue" class="panel-mode-tag">{{ isEditMode ? 'EDIT MODE' : 'CREATE MODE' }}</a-tag>
        <a-tag v-if="isDirty" color="orange" bordered class="panel-mode-tag">未保存</a-tag>
      </a-space>
    </div>

    <a-form ref="formRef" :model="form" :rules="rules" layout="vertical" class="panel-form">
      <div class="section-title">基础信息</div>
      <a-form-item field="name" label="名称" required>
        <a-input v-model="form.name" placeholder="请输入智能体名称" />
      </a-form-item>

      <a-form-item field="description" label="描述">
        <a-textarea v-model="form.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
      </a-form-item>

      <a-form-item field="prompt_template" label="提示词" required>
        <a-textarea
          v-model="form.prompt_template"
          :auto-size="{ minRows: 6, maxRows: 10 }"
          placeholder="请输入 Prompt Template"
        />
      </a-form-item>

      <div class="section-title">能力绑定</div>
      <a-form-item field="skills" label="Skills 绑定">
        <a-select
          v-model="form.skills"
          placeholder="请选择 Skills"
          :loading="skillsLoading"
          :options="skillSelectOptions"
          multiple
          allow-clear
          :max-tag-count="2"
        />
      </a-form-item>

      <a-form-item field="mcpTools" label="MCP Tools 绑定">
        <template #extra>
          <a-space size="mini">
            <a-link @click="goMcpManagement">去管理</a-link>
            <a-link @click="fetchSkills">刷新</a-link>
          </a-space>
        </template>
        <a-select
          v-model="form.mcpTools"
          placeholder="请选择 MCP Tools"
          :loading="skillsLoading"
          :options="mcpSelectOptions"
          multiple
          allow-clear
          :max-tag-count="2"
        />
      </a-form-item>

      <div class="section-title">知识库</div>
      <a-form-item field="knowledgeFiles" label="专属知识库">
        <a-upload
          v-model:file-list="uploadFileList"
          :auto-upload="false"
          multiple
          :limit="5"
          accept=".pdf,.doc,.docx,.txt"
          @change="onFileChange"
        >
          <template #upload-button>
            <a-button type="outline">选择文件</a-button>
          </template>
        </a-upload>

        <div class="upload-tip">支持 PDF/DOC/DOCX/TXT，最多 5 个文件，保存后自动入库</div>

        <div v-if="form.knowledgeFiles.length" class="upload-list">
          <div v-for="file in form.knowledgeFiles" :key="file.name" class="upload-item">
            <span>{{ file.name }}</span>
          </div>
        </div>

        <div v-if="uploadResults.length" class="upload-result">
          <div class="upload-summary-row">
            <div class="upload-summary">本次新增 {{ uploadSummary.docCount }} 个文档，共 {{ uploadSummary.chunkCount }} 段</div>
            <a-button type="text" size="mini" @click="uploadDetailExpanded = !uploadDetailExpanded">
              {{ uploadDetailExpanded ? '收起明细' : '查看明细' }}
            </a-button>
          </div>
          <div v-if="uploadDetailExpanded" class="upload-detail-list">
            <div v-for="item in uploadResults" :key="item.doc_id">
              文档 {{ item.doc_id }}：{{ item.chunk_count }} 段（v{{ item.version }}）
            </div>
          </div>
        </div>

        <div v-if="isEditMode" class="knowledge-manage-block">
          <div class="knowledge-manage-header">
            <div class="knowledge-manage-title">已入库文档（{{ documents.length }}）</div>
            <a-space size="mini">
              <a-input
                v-model="docKeyword"
                size="mini"
                allow-clear
                placeholder="按文档名/ID筛选"
                style="width: 180px"
              />
              <a-button
                size="mini"
                type="outline"
                :loading="purgePolling"
                :disabled="documentsLoading || batchDeleting || !!deletingDocId || deletedDocumentsCount === 0"
                @click="onPurgeDeletedDocuments"
              >
                清理已软删（{{ deletedDocumentsCount }}）
              </a-button>
              <a-button
                size="mini"
                :disabled="!documents.length"
                @click="selectedDocumentIds = allDocumentsChecked ? [] : documents.map((item) => item.doc_id)"
              >
                {{ allDocumentsChecked ? '取消全选' : '全选' }}
              </a-button>
              <a-button
                size="mini"
                status="danger"
                :loading="batchDeleting"
                :disabled="!selectedDocumentIds.length || !!deletingDocId"
                @click="onBatchDeleteDocuments()"
              >
                批量删除（{{ selectedDocumentIds.length }}）
              </a-button>
            </a-space>
          </div>

          <div v-if="purgeTaskMessage" class="purge-task-status">
            <a-tag :color="purgeTaskState === 'SUCCESS' ? 'green' : purgeTaskState === 'FAILURE' ? 'red' : 'arcoblue'">
              {{ purgeTaskState || 'PENDING' }}
            </a-tag>
            <span>{{ purgeTaskMessage }}</span>
          </div>

          <div class="knowledge-filter">
            <a-input
              v-model="docKeyword"
              size="small"
              allow-clear
              placeholder="按文档名/ID筛选"
            />
            <a-switch v-model="onlyShowDeleted" size="small" />
            <span class="filter-label">仅看已软删</span>
            <span class="filter-count">{{ filteredCountLabel }}</span>
            <a-button
              size="mini"
              type="outline"
              :disabled="!filteredDocuments.length"
              :loading="batchDeleting"
              @click="onBatchDeleteDocuments(filteredDocuments.map((item) => item.doc_id))"
            >
              删除筛选结果（{{ filteredDocuments.length }}）
            </a-button>
          </div>

          <a-spin :loading="documentsLoading">
            <div v-if="filteredDocuments.length" class="knowledge-doc-list">
              <div v-for="doc in filteredDocuments" :key="doc.doc_id" class="knowledge-doc-item">
                <div class="knowledge-doc-main-wrap">
                  <a-checkbox
                    :model-value="selectedDocumentIds.includes(doc.doc_id)"
                    @change="(checked: boolean | string | number) => {
                      const enabled = Boolean(checked)
                      if (enabled) {
                        if (!selectedDocumentIds.includes(doc.doc_id)) selectedDocumentIds.push(doc.doc_id)
                      } else {
                        selectedDocumentIds = selectedDocumentIds.filter((id) => id !== doc.doc_id)
                      }
                    }"
                  />
                  <div class="knowledge-doc-main">
                    <div class="knowledge-doc-name" v-html="highlightText(String(doc.source || doc.doc_id))" />
                    <div class="knowledge-doc-meta" v-html="highlightText(`${doc.doc_id} · v${doc.version} · ${doc.chunk_count} 段`)" />
                  </div>
                </div>
                <a-button
                  type="text"
                  size="mini"
                  status="danger"
                  :loading="deletingDocId === doc.doc_id"
                  :disabled="batchDeleting || (!!deletingDocId && deletingDocId !== doc.doc_id)"
                  @click="onDeleteDocument(doc)"
                >
                  删除
                </a-button>
              </div>
            </div>
            <a-empty v-else description="暂无已入库文档" />
          </a-spin>
        </div>
      </a-form-item>

      <a-form-item field="is_public" label="是否公开">
        <a-switch v-model="form.is_public" />
      </a-form-item>

      <div class="actions-placeholder" />
    </a-form>

    <div class="actions sticky-actions">
      <a-space>
        <a-button @click="emit('cancel')">取消</a-button>
        <a-tooltip content="快捷键：Ctrl/Cmd + S">
          <a-button type="primary" :loading="loading || uploading" @click="onSubmit">
            {{ isEditMode ? '保存更改' : '创建智能体' }}
          </a-button>
        </a-tooltip>
      </a-space>
    </div>
  </div>
</template>

<style scoped>
.glass-panel {
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
  border-radius: var(--radius-xl);
}

.agent-form-panel {
  padding: 0;
  overflow: hidden;
}

.panel-head {
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: linear-gradient(135deg, rgba(109, 94, 248, 0.16), rgba(39, 211, 195, 0.08));
}

.panel-head-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
}

:deep(.panel-mode-tag),
:deep(.panel-mode-tag .arco-tag-content) {
  color: #000000 !important;
  background: rgba(255, 255, 255, 0.92) !important;
  border-color: rgba(0, 0, 0, 0.25) !important;
}

.panel-form {
  padding: 18px 20px 20px;
}

:deep(.arco-form-item-label-col > label),
:deep(.arco-form-item-extra),
:deep(.arco-form-item-message),
:deep(.arco-upload-list-item-name) {
  color: #ffffff !important;
  opacity: 1 !important;
}

/* 指定区域的控件文字改为黑色（用户要求） */
:deep(.arco-select-view-value),
:deep(.arco-select-view-placeholder),
:deep(.arco-input),
:deep(.arco-input::placeholder),
:deep(.arco-textarea::placeholder),
:deep(.arco-btn),
:deep(.arco-btn span),
:deep(.arco-tag),
:deep(.arco-tag span) {
  color: #111827 !important;
  opacity: 1 !important;
}

:deep(.arco-input-wrapper),
:deep(.arco-textarea-wrapper),
:deep(.arco-select-view) {
  border-color: rgba(64, 141, 255, 0.9) !important;
  background: rgba(56, 126, 245, 0.3) !important;
  color: #111827 !important;
}

:deep(.arco-input-wrapper:hover),
:deep(.arco-textarea-wrapper:hover),
:deep(.arco-select-view:hover) {
  border-color: rgba(128, 187, 255, 0.95) !important;
  background: rgba(56, 126, 245, 0.4) !important;
}

:deep(.arco-upload-list-item),
:deep(.arco-btn-outline),
:deep(.arco-btn-text),
:deep(.arco-btn) {
  border-color: rgba(0, 0, 0, 0.35) !important;
  background: rgba(255, 255, 255, 0.88) !important;
  color: #111827 !important;
}

:deep(.arco-btn-outline:hover),
:deep(.arco-btn-text:hover) {
  border-color: rgba(255, 255, 255, 0.85) !important;
  background: rgba(8, 20, 46, 0.5) !important;
}

.section-title {
  margin: 8px 0 10px;
  padding-left: 10px;
  border-left: 3px solid rgba(79, 140, 255, 0.9);
  font-size: 13px;
  font-weight: 700;
  color: #ffffff;
  text-shadow: 0 1px 6px rgba(10, 24, 58, 0.35);
}

.upload-tip {
  margin-top: 8px;
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  text-shadow: 0 1px 8px rgba(8, 18, 42, 0.35);
}

.upload-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-item {
  color: #ffffff;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  font-weight: 600;
}

.upload-result {
  margin-top: 8px;
  color: #8ef4de;
  font-size: 12px;
}

.upload-item,
.knowledge-doc-item {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.upload-item:hover,
.knowledge-doc-item:hover {
  transform: translateY(-1px);
  border-color: rgba(79, 140, 255, 0.5);
  box-shadow: 0 12px 22px rgba(13, 32, 74, 0.3);
}

.upload-summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.upload-summary {
  font-weight: 600;
}

.upload-detail-list {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 160px;
  overflow-y: auto;
  padding-right: 4px;
}

.knowledge-manage-block {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed rgba(255, 255, 255, 0.24);
}

.knowledge-manage-header {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.knowledge-manage-title {
  font-weight: 600;
  color: var(--text-1);
}

.knowledge-filter {
  margin: 10px 0 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.filter-label {
  color: #ffffff;
  font-size: 12px;
}

.filter-count {
  color: #ffffff;
  font-size: 12px;
}

.keyword-hit {
  background: rgba(109, 94, 248, 0.26);
  color: var(--text-1);
  padding: 0 3px;
  border-radius: 4px;
}

.knowledge-doc-name :deep(mark.keyword-hit),
.knowledge-doc-meta :deep(mark.keyword-hit) {
  background: rgba(109, 94, 248, 0.26);
  color: var(--text-1);
}

.knowledge-doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 220px;
  overflow-y: auto;
  padding-right: 4px;
}

.purge-task-status {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-2);
  display: flex;
  align-items: center;
  gap: 8px;
}

.knowledge-doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.12);
}

.knowledge-doc-main-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.knowledge-doc-main {
  min-width: 0;
}

.knowledge-doc-name {
  font-size: 13px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.knowledge-doc-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-3);
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.actions-placeholder {
  height: 56px;
}

.sticky-actions {
  position: sticky;
  bottom: 0;
  z-index: 6;
  padding: 10px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  background: linear-gradient(180deg, rgba(22, 30, 58, 0.1), rgba(22, 30, 58, 0.75));
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

:deep(.arco-upload-list-item-name),
:deep(.arco-form-item-label-col > label),
:deep(.arco-link),
:deep(.arco-btn-text),
:deep(.arco-btn-outline),
:deep(.arco-upload-trigger),
:deep(.arco-upload-trigger .arco-btn),
:deep(.arco-select-view-single .arco-select-view-value),
:deep(.arco-select-view-multiple .arco-tag-content),
:deep(.arco-input::placeholder),
:deep(.arco-textarea::placeholder) {
  color: #ffffff !important;
}

:deep(.arco-btn-outline),
:deep(.arco-btn-text) {
  border-color: rgba(255, 255, 255, 0.4) !important;
  background: rgba(255, 255, 255, 0.06) !important;
}

:deep(.arco-btn-outline:hover),
:deep(.arco-btn-text:hover) {
  background: rgba(255, 255, 255, 0.14) !important;
  border-color: rgba(255, 255, 255, 0.62) !important;
}
</style>
