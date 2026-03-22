<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  SkillItem,
  SkillSourceType,
  disableSkill,
  enableSkill,
  deleteSkill,
  getSkillTaskStatus,
  getSkills,
  loadSkill,
  uploadLocalSkill,
} from '../api/skills'

const loading = ref(false)
const skills = ref<SkillItem[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const drawerVisible = ref(false)

const loadForm = reactive({
  source_type: '' as SkillSourceType | '',
  source_url: '',
  source_version: '',
  uploadFile: null as File | null,
})

const taskPolling = reactive({
  taskId: '',
  status: '',
  polling: false,
  skillId: '',
  error: '',
  startedAt: 0,
  timeoutMs: 180000,
})

let taskPollingTimer: number | null = null

const showSourceUrl = computed(() =>
  ['github', 'npm', 'http', 'private_registry'].includes(loadForm.source_type)
)

const showUpload = computed(() => loadForm.source_type === 'local')

const isUnsupportedSource = computed(() =>
  ['npm', 'private_registry'].includes(loadForm.source_type)
)

const sourceOptions = [
  { label: 'GitHub', value: 'github' },
  { label: 'NPM（暂不支持）', value: 'npm' },
  { label: 'HTTP', value: 'http' },
  { label: '本地包', value: 'local' },
  { label: '私有 Registry（暂不支持）', value: 'private_registry' },
]

const columns = [
  { title: '名称', dataIndex: 'name' },
  { title: '技能标识', dataIndex: 'skill_id' },
  { title: '类型', dataIndex: 'category' },
  { title: '来源', dataIndex: 'source_type' },
  { title: '版本', dataIndex: 'version' },
  { title: '状态', dataIndex: 'status', slotName: 'status' },
  { title: '操作', dataIndex: 'actions', slotName: 'actions' },
]

const safeSkills = computed(() => (Array.isArray(skills.value) ? skills.value : []))

const stopTaskPolling = () => {
  if (taskPollingTimer) {
    window.clearInterval(taskPollingTimer)
    taskPollingTimer = null
  }
  taskPolling.polling = false
}

const resetTaskPolling = () => {
  stopTaskPolling()
  taskPolling.taskId = ''
  taskPolling.status = ''
  taskPolling.skillId = ''
  taskPolling.error = ''
  taskPolling.startedAt = 0
}

const fetchSkills = async () => {
  loading.value = true
  try {
    const data = await getSkills({
      page: pagination.page,
      page_size: pagination.pageSize,
    })
    const list = Array.isArray(data?.list)
      ? data.list
      : Array.isArray(data?.data?.list)
        ? data.data.list
        : []
    skills.value = list as SkillItem[]
    pagination.total = data?.total ?? data?.data?.total ?? 0
  } catch (error: any) {
    Message.error(error?.message || '获取技能列表失败')
  } finally {
    loading.value = false
  }
}

const onPageChange = (page: number) => {
  pagination.page = page
  fetchSkills()
}

const onDisableSkill = (row: SkillItem) => {
  Modal.confirm({
    title: '确认禁用该技能？',
    content: `禁用后技能将不可用：${row.name}（${row.skill_id}）`,
    onOk: async () => {
      try {
        await disableSkill(row.id, { reason: '手动禁用' })
        Message.success('技能已禁用')
        fetchSkills()
      } catch (error: any) {
        Message.error(getErrorDetail(error, '禁用失败'))
      }
    },
  })
}

const onEnableSkill = (row: SkillItem) => {
  Modal.confirm({
    title: '确认启用该技能？',
    content: `启用后技能可被调用：${row.name}（${row.skill_id}）`,
    onOk: async () => {
      try {
        await enableSkill(row.id)
        Message.success('技能已启用')
        fetchSkills()
      } catch (error: any) {
        Message.error(getErrorDetail(error, '启用失败'))
      }
    },
  })
}

const onDeleteSkill = (row: SkillItem) => {
  Modal.confirm({
    title: '确认删除该技能？',
    content: `删除后不可恢复：${row.name}（${row.skill_id}）`,
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        await deleteSkill(row.id)
        Message.success('技能已删除')
        fetchSkills()
      } catch (error: any) {
        Message.error(getErrorDetail(error, '删除失败'))
      }
    },
  })
}

const pollTaskStatusOnce = async () => {
  if (!taskPolling.taskId) return

  if (taskPolling.startedAt && Date.now() - taskPolling.startedAt > taskPolling.timeoutMs) {
    taskPolling.error = '任务轮询超时（3 分钟），请稍后手动刷新列表确认结果'
    Message.warning(taskPolling.error)
    stopTaskPolling()
    return
  }

  try {
    const res = await getSkillTaskStatus(taskPolling.taskId)
    const status = String(res?.status || '').toUpperCase()
    taskPolling.status = status || 'PENDING'

    if (status === 'SUCCESS') {
      Message.success('技能加载完成')
      resetTaskPolling()
      fetchSkills()
      return
    }

    if (status === 'FAILURE' || status === 'REVOKED') {
      taskPolling.error = String(res?.error || '任务执行失败')
      Message.error(`技能加载失败：${taskPolling.error}`)
      resetTaskPolling()
      fetchSkills()
      return
    }
  } catch (error: any) {
    stopTaskPolling()
    taskPolling.error = error?.message || '任务状态查询失败'
    Message.error(taskPolling.error)
  }
}

const startTaskPolling = () => {
  stopTaskPolling()
  taskPolling.polling = true
  taskPolling.startedAt = Date.now()

  pollTaskStatusOnce()
  taskPollingTimer = window.setInterval(() => {
    pollTaskStatusOnce()
  }, 2000)
}

const onStopTaskPolling = () => {
  stopTaskPolling()
  taskPolling.error = '已手动停止轮询，可稍后刷新列表查看任务结果'
  Message.info(taskPolling.error)
}

const onNativeFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  loadForm.uploadFile = file
}

const resetLoadForm = () => {
  loadForm.source_type = ''
  loadForm.source_url = ''
  loadForm.source_version = ''
  loadForm.uploadFile = null
}

const getErrorDetail = (error: any, fallback: string) => {
  return error?.response?.data?.detail || error?.response?.data?.message || error?.message || fallback
}

const onSubmitLoad = async () => {
  if (!loadForm.source_type) {
    Message.warning('请选择来源类型')
    return
  }
  if (isUnsupportedSource.value) {
    Message.warning('当前版本暂不支持该来源类型')
    return
  }
  if (showSourceUrl.value && !loadForm.source_url.trim()) {
    Message.warning('请输入来源地址')
    return
  }
  if (showUpload.value && !loadForm.uploadFile) {
    Message.warning('请上传 .skill 或 .zip 技能归档包')
    return
  }

  try {
    const task = showUpload.value
      ? await uploadLocalSkill({
          file: loadForm.uploadFile as File,
          source_version: loadForm.source_version.trim() || undefined,
        })
      : await loadSkill({
          source_type: loadForm.source_type as SkillSourceType,
          source_url: loadForm.source_url.trim() || undefined,
          source_version: loadForm.source_version.trim() || undefined,
        })

    taskPolling.taskId = task.task_id
    taskPolling.skillId = task.skill_id
    taskPolling.status = String(task.status || 'PENDING').toUpperCase()
    taskPolling.error = ''

    Message.success('已提交异步加载任务，正在轮询任务状态')
    drawerVisible.value = false
    resetLoadForm()
    fetchSkills()
    startTaskPolling()
  } catch (error: any) {
    Message.error(getErrorDetail(error, '加载失败'))
  }
}

onMounted(() => {
  fetchSkills()
})

onUnmounted(() => {
  stopTaskPolling()
})
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <div class="title">技能管理</div>
        <div class="subtitle">查看技能状态并上传 .skill/.zip 技能归档包</div>
      </div>
      <div class="actions">
        <a-button type="primary" @click="drawerVisible = true">加载外部技能</a-button>
      </div>
    </div>

    <a-alert v-if="taskPolling.taskId" type="info" class="task-alert" :show-icon="true">
      <template #title>异步加载任务执行中</template>
      <div class="task-alert-content">
        <span>任务 ID：{{ taskPolling.taskId }}，当前状态：{{ taskPolling.status || 'PENDING' }}</span>
        <a-button size="mini" type="outline" status="warning" @click="onStopTaskPolling">
          停止轮询
        </a-button>
      </div>
    </a-alert>

    <a-table
      :data="safeSkills"
      :columns="columns"
      :pagination="false"
      :loading="loading"
      row-key="id"
      class="table"
      :bordered="true"
      :scroll="{ x: 980 }"
    >
      <template #status="{ record }">
        <a-tag :color="record.status === 'active' ? 'green' : 'gray'">
          {{ record.status === 'active' ? '启用' : '禁用' }}
        </a-tag>
      </template>
      <template #actions="{ record }">
        <a-space>
          <a-button
            v-if="record.status === 'active'"
            size="mini"
            type="outline"
            status="danger"
            @click="onDisableSkill(record)"
          >
            禁用
          </a-button>
          <a-button
            v-else
            size="mini"
            type="outline"
            status="success"
            @click="onEnableSkill(record)"
          >
            启用
          </a-button>
          <a-button
            size="mini"
            type="outline"
            status="danger"
            @click="onDeleteSkill(record)"
          >
            删除
          </a-button>
        </a-space>
      </template>
    </a-table>

    <div class="pagination">
      <a-pagination
        :current="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        show-total
        @change="onPageChange"
      />
    </div>

    <a-drawer
      v-model:visible="drawerVisible"
      title="加载外部技能"
      :width="420"
      @close="resetLoadForm"
      @ok="onSubmitLoad"
    >
      <a-form :model="loadForm" layout="vertical">
        <a-form-item label="来源类型">
          <a-select
            v-model="loadForm.source_type"
            placeholder="请选择来源类型"
            :options="sourceOptions"
          />
          <div v-if="isUnsupportedSource" class="form-tip">
            npm / private_registry 暂未开放，后端会返回 422。
          </div>
        </a-form-item>

        <a-form-item label="版本（可选）">
          <a-input v-model="loadForm.source_version" placeholder="例如：v1.0.0" />
        </a-form-item>

        <a-form-item v-if="showSourceUrl" label="来源地址">
          <a-input v-model="loadForm.source_url" placeholder="请输入来源地址" />
        </a-form-item>

        <a-form-item v-if="showUpload" label="本地技能归档包">
          <input
            type="file"
            accept=".skill,.zip"
            @change="onNativeFileChange"
          />
          <div class="form-tip-muted">支持上传 .skill 或 .zip 技能归档包；支持“单一顶层目录”或“根目录”打包方式，但必须包含 SKILL.md，并含 name/description 字段。</div>
        </a-form-item>
      </a-form>
    </a-drawer>
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
  flex-wrap: wrap;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.subtitle {
  color: #6b7280;
  font-size: 12px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.task-alert {
  margin-bottom: 4px;
}

.task-alert-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.table :deep(.arco-table-header) {
  background: #f8fafc;
}

.table :deep(.arco-table-td) {
  color: #111827;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.muted {
  color: #9ca3af;
  font-size: 12px;
}

.form-tip {
  margin-top: 8px;
  color: #ef4444;
  font-size: 12px;
}

.form-tip-muted {
  margin-top: 8px;
  color: #6b7280;
  font-size: 12px;
}
</style>
