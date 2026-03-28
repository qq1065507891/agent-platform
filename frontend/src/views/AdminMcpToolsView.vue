<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  createMcpTool,
  deleteMcpTool,
  getMcpTools,
  importMcpTools,
  testMcpTool,
  updateMcpTool,
  type McpImportResultItem,
  type McpToolItem,
  type McpTransport,
} from '../api/mcpTools'

const loading = ref(false)
const creating = ref(false)
const importing = ref(false)
const tableData = ref<McpToolItem[]>([])
const importFile = ref<File | null>(null)
const importOverwrite = ref(false)
const importResults = ref<McpImportResultItem[]>([])
const importSummary = ref({ imported_count: 0, failed_count: 0 })

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const form = reactive({
  name: '',
  description: '',
  transport: 'http' as McpTransport,
  endpoint_url: '',
  command: '',
  enabled: true,
})

const transportOptions = [
  { label: 'HTTP', value: 'http' },
  { label: 'SSE', value: 'sse' },
  { label: 'STDIO', value: 'stdio' },
]

const columns = [
  { title: '名称', dataIndex: 'name' },
  { title: 'Skill ID', dataIndex: 'skill_id' },
  { title: '传输协议', dataIndex: 'transport' },
  { title: '状态', dataIndex: 'status', slotName: 'status' },
  { title: '创建时间', dataIndex: 'created_at' },
  { title: '操作', dataIndex: 'actions', slotName: 'actions', width: 320 },
]

const showEndpoint = computed(() => form.transport === 'http' || form.transport === 'sse')
const showCommand = computed(() => form.transport === 'stdio')

const fetchList = async () => {
  loading.value = true
  try {
    const res = await getMcpTools({ page: pagination.page, page_size: pagination.pageSize })
    const list = Array.isArray(res?.list)
      ? res.list
      : Array.isArray(res?.data?.list)
        ? res.data.list
        : []
    tableData.value = list
    pagination.total = Number(res?.total ?? res?.data?.total ?? 0)
  } catch (error: any) {
    Message.error(error?.message || '获取 MCP 工具列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.transport = 'http'
  form.endpoint_url = ''
  form.command = ''
  form.enabled = true
}

const onCreate = async () => {
  if (!form.name.trim()) {
    Message.warning('请输入名称')
    return
  }
  if (showEndpoint.value && !form.endpoint_url.trim()) {
    Message.warning('请输入 endpoint_url')
    return
  }
  if (showCommand.value && !form.command.trim()) {
    Message.warning('请输入 command')
    return
  }

  creating.value = true
  try {
    await createMcpTool({
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      transport: form.transport,
      endpoint_url: showEndpoint.value ? form.endpoint_url.trim() : undefined,
      command: showCommand.value ? form.command.trim() : undefined,
      enabled: form.enabled,
    })
    Message.success('MCP 工具创建成功')
    resetForm()
    fetchList()
  } catch (error: any) {
    Message.error(error?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

const onToggleStatus = (row: McpToolItem) => {
  const nextEnabled = row.status !== 'active'
  Modal.confirm({
    title: nextEnabled ? '确认启用该 MCP 工具？' : '确认禁用该 MCP 工具？',
    content: `${row.name}（${row.skill_id}）`,
    onOk: async () => {
      try {
        await updateMcpTool(row.id, { enabled: nextEnabled })
        Message.success(nextEnabled ? '已启用' : '已禁用')
        fetchList()
      } catch (error: any) {
        Message.error(error?.message || '操作失败')
      }
    },
  })
}

const onDelete = (row: McpToolItem) => {
  Modal.confirm({
    title: '确认删除该 MCP 工具？',
    content: `${row.name}（${row.skill_id}）删除后不可恢复`,
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        await deleteMcpTool(row.id)
        Message.success('删除成功')
        fetchList()
      } catch (error: any) {
        Message.error(error?.message || '删除失败')
      }
    },
  })
}

const onTest = async (row: McpToolItem) => {
  try {
    const res = await testMcpTool(row.id)
    Message.info(`${res.ok ? '成功' : '失败'}：${res.message}（${res.latency_ms}ms）`)
  } catch (error: any) {
    const rawMessage = String(error?.message || '')
    const matched = rawMessage.match(/请\s*(\d+)s\s*后再试/)
    if (matched?.[1]) {
      Message.warning(`测试过于频繁，请等待 ${matched[1]} 秒后重试`)
      return
    }
    Message.error(rawMessage || '测试失败')
  }
}

const onPageChange = (page: number) => {
  pagination.page = page
  fetchList()
}

const onImportFileChange = (fileList: any[]) => {
  if (!fileList?.length) {
    importFile.value = null
    return
  }
  importFile.value = fileList[0]?.file || null
}

const onImport = async () => {
  if (!importFile.value) {
    Message.warning('请先选择 JSON 文件')
    return
  }
  importing.value = true
  try {
    const payload = await importMcpTools(importFile.value, importOverwrite.value)
    importSummary.value = {
      imported_count: Number(payload?.imported_count || 0),
      failed_count: Number(payload?.failed_count || 0),
    }
    importResults.value = Array.isArray(payload?.results) ? payload.results : []
    Message.success(`导入完成：成功 ${importSummary.value.imported_count}，失败 ${importSummary.value.failed_count}`)
    fetchList()
  } catch (error: any) {
    Message.error(error?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(fetchList)
</script>

<template>
  <div class="admin-page">
    <section class="hero glass-panel">
      <div>
        <div class="title">MCP 工具管理</div>
        <div class="subtitle">全局维护 MCP 工具，供智能体绑定使用</div>
      </div>
      <a-button @click="fetchList">刷新列表</a-button>
    </section>

    <a-card title="文件导入 MCP 工具（JSON）" class="import-card">
      <a-space direction="vertical" fill>
        <a-upload
          :auto-upload="false"
          :limit="1"
          accept=".json"
          @change="onImportFileChange"
        >
          <template #upload-button>
            <a-button type="outline">选择 JSON 文件</a-button>
          </template>
        </a-upload>
        <a-space>
          <a-checkbox v-model="importOverwrite">覆盖同名工具</a-checkbox>
          <a-button type="primary" :loading="importing" @click="onImport">开始导入</a-button>
        </a-space>
        <div v-if="importResults.length" class="import-result-box">
          <div class="import-summary">
            成功 {{ importSummary.imported_count }} 条，失败 {{ importSummary.failed_count }} 条
          </div>
          <div class="import-result-list">
            <div v-for="(row, idx) in importResults" :key="idx" :class="row.ok ? 'ok' : 'fail'">
              #{{ row.index }} {{ row.name || '未命名' }} - {{ row.ok ? '成功' : `失败：${row.error || '未知错误'}` }}
            </div>
          </div>
        </div>
      </a-space>
    </a-card>

    <a-card title="手动新增 MCP 工具" class="create-card">
      <a-form :model="form" layout="vertical">
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="名称" required>
              <a-input v-model="form.name" placeholder="如 weather-mcp" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="传输协议" required>
              <a-select v-model="form.transport" :options="transportOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="是否启用">
              <a-switch v-model="form.enabled" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="描述">
          <a-input v-model="form.description" placeholder="可选" />
        </a-form-item>

        <a-form-item v-if="showEndpoint" label="Endpoint URL" required>
          <a-input v-model="form.endpoint_url" placeholder="https://mcp.example.com" />
        </a-form-item>

        <a-form-item v-if="showCommand" label="Command" required>
          <a-input v-model="form.command" placeholder="python -m xxx" />
        </a-form-item>

        <a-button type="primary" :loading="creating" @click="onCreate">创建</a-button>
      </a-form>
    </a-card>

    <a-table
      row-key="id"
      :loading="loading"
      :columns="columns"
      :data="tableData"
      :pagination="false"
      :bordered="true"
    >
      <template #status="{ record }">
        <a-tag :color="record.status === 'active' ? 'green' : 'gray'">
          {{ record.status === 'active' ? '启用' : '禁用' }}
        </a-tag>
      </template>

      <template #actions="{ record }">
        <a-space>
          <a-button size="mini" type="outline" @click="onTest(record)">测试连接</a-button>
          <a-button
            size="mini"
            :status="record.status === 'active' ? 'warning' : 'success'"
            type="outline"
            @click="onToggleStatus(record)"
          >
            {{ record.status === 'active' ? '禁用' : '启用' }}
          </a-button>
          <a-button size="mini" type="outline" status="danger" @click="onDelete(record)">删除</a-button>
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
  </div>
</template>

<style scoped>
.admin-page {
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
  padding: 18px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background-image: linear-gradient(135deg, rgba(109, 94, 248, 0.22), rgba(39, 211, 195, 0.1));
}

.title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.subtitle {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 4px;
}

.import-card,
.create-card {
  margin-bottom: 4px;
}

.import-result-box {
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  padding: 8px;
  max-height: 180px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.06);
}

.import-summary {
  font-weight: 600;
  margin-bottom: 6px;
}

.import-result-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.ok {
  color: #49e7c1;
}

.fail {
  color: #ff8f9f;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
