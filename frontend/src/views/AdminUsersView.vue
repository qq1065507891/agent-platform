<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { createUser, getUsers, importUsers, updateUser } from '../api/users'
import { getRoles } from '../api/roles'
import { getApiErrorMessage } from '../utils/request'
import { buildPageParams, extractPagedList } from '../utils/pagination'

interface UserRow {
  id?: string
  _rowKey?: string
  username: string
  email: string
  role: string
  status: 'active' | 'disabled'
  created_at?: string
}

const normalizeRow = (item: UserRow): UserRow => ({
  ...item,
  _rowKey: item.id || item._rowKey || `${item.username}-${item.email}`,
})

interface RoleOption {
  label: string
  value: string
}

const loading = ref(false)
const keyword = ref('')
const users = ref<UserRow[]>([])
const tableData = ref<UserRow[]>([])
const roles = ref<RoleOption[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

const safeUsers = computed(() => (Array.isArray(users.value) ? [...users.value] : []))

const tableKey = computed(() => `users-${safeUsers.value.length}`)

const columns = [
  { title: '用户名', dataIndex: 'username' },
  { title: '邮箱', dataIndex: 'email' },
  { title: '角色', dataIndex: 'role', slotName: 'role' },
  { title: '状态', dataIndex: 'status', slotName: 'status' },
  { title: '创建时间', dataIndex: 'created_at', slotName: 'created_at' },
]

const createVisible = ref(false)
const importVisible = ref(false)
const createForm = reactive({
  username: '',
  email: '',
  password: '',
  role: 'user',
  status: 'active' as 'active' | 'disabled',
})

const importForm = reactive({
  text: '',
})

const fetchRoles = async () => {
  try {
    const data = await getRoles()
    const list = Array.isArray(data) ? data : data?.list
    roles.value = (list || []).map((item: any) => ({ label: item.name, value: item.name }))
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '获取角色失败'))
  }
}

const fetchUsers = async () => {
  loading.value = true
  try {
    const data = await getUsers(
      buildPageParams(pagination, {
        keyword: keyword.value || undefined,
      })
    )
    const { list, total } = extractPagedList<UserRow>(data)
    users.value = list.map((item) => normalizeRow(item))
    tableData.value = users.value
    pagination.total = total
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '获取用户失败'))
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  pagination.page = 1
  fetchUsers()
}

const onPageChange = (page: number) => {
  pagination.page = page
  fetchUsers()
}

const updateUserField = async (
  row: UserRow,
  patch: { status?: 'active' | 'disabled'; role?: string },
  onSuccess: () => void,
) => {
  if (!row.id) {
    Message.error('用户ID缺失，无法更新')
    return
  }
  try {
    await updateUser(row.id, patch)
    onSuccess()
    Message.success('更新成功')
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '更新失败'))
  }
}

const onStatusChange = async (row: UserRow, status: 'active' | 'disabled') => {
  await updateUserField(row, { status }, () => {
    row.status = status
  })
}

const onRoleChange = async (row: UserRow, role: string) => {
  await updateUserField(row, { role }, () => {
    row.role = role
  })
}

const onCreateUser = async () => {
  if (!createForm.username || !createForm.email || !createForm.password) {
    Message.warning('请完整填写信息')
    return
  }
  try {
    const created = await createUser({
      username: createForm.username,
      email: createForm.email,
      password: createForm.password,
      role: createForm.role,
      status: createForm.status,
    })
    if (created) {
      users.value = [normalizeRow(created as UserRow), ...users.value]
      tableData.value = users.value
      pagination.total += 1
    }
    Message.success('创建成功')
    createVisible.value = false
    createForm.username = ''
    createForm.email = ''
    createForm.password = ''
    createForm.role = 'user'
    createForm.status = 'active'
    keyword.value = ''
    pagination.page = 1
    fetchUsers()
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '创建失败'))
  }
}

const parseImportUsers = () => {
  if (!importForm.text.trim()) return []
  try {
    const parsed = JSON.parse(importForm.text)
    if (Array.isArray(parsed)) {
      return parsed
    }
  } catch (error) {
    return []
  }
  return []
}

const onImportUsers = async () => {
  const list = parseImportUsers()
  if (!list.length) {
    Message.warning('请输入合法的 JSON 数组')
    return
  }
  try {
    const data = await importUsers({ users: list })
    Message.success(`导入完成：成功 ${data.success} 条，失败 ${data.failed} 条`)
    importVisible.value = false
    importForm.text = ''
    fetchUsers()
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '导入失败'))
  }
}

onMounted(() => {
  fetchRoles()
  fetchUsers()
})
</script>

<template>
  <div class="admin-page">
    <section class="hero glass-panel">
      <div>
        <div class="title">用户管理</div>
        <div class="subtitle">管理用户角色与状态</div>
      </div>
      <div class="hero-actions">
        <a-button type="primary" @click="createVisible = true">新增用户</a-button>
        <a-button type="outline" @click="importVisible = true">批量导入</a-button>
      </div>
    </section>

    <div class="toolbar glass-panel">
      <a-input-search
        v-model="keyword"
        placeholder="搜索用户名/邮箱"
        allow-clear
        @search="onSearch"
      />
    </div>

    <a-table
      :key="tableKey"
      :data="safeUsers"
      :columns="columns"
      :pagination="false"
      :loading="loading"
      row-key="_rowKey"
      class="table"
      :bordered="true"
      :scroll="{ x: 900 }"
    >
      <template #role="{ record }">
        <a-select
          :model-value="record.role"
          :options="roles"
          size="small"
          @change="(value: string | number | boolean) => onRoleChange(record, String(value))"
        />
      </template>
      <template #status="{ record }">
        <a-select
          :model-value="record.status"
          size="small"
          :options="[
            { label: '启用', value: 'active' },
            { label: '禁用', value: 'disabled' },
          ]"
          @change="(value: string | number | boolean) => onStatusChange(record, String(value) as 'active' | 'disabled')"
        />
      </template>
      <template #created_at="{ record }">
        <span>{{ record.created_at || '-' }}</span>
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

    <a-modal
      v-model:visible="createVisible"
      title="新增用户"
      ok-text="创建"
      @ok="onCreateUser"
    >
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model="createForm.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input v-model="createForm.email" placeholder="请输入邮箱" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model="createForm.password" placeholder="请输入初始密码" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model="createForm.role" :options="roles" />
        </a-form-item>
        <a-form-item label="状态">
          <a-select
            v-model="createForm.status"
            :options="[
              { label: '启用', value: 'active' },
              { label: '禁用', value: 'disabled' },
            ]"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:visible="importVisible"
      title="批量导入"
      ok-text="导入"
      @ok="onImportUsers"
    >
      <div class="import-tip">
        请输入用户数组 JSON（建议一次不超过 200 条）。
      </div>
      <div class="import-sample">
        <div class="import-sample-title">示例</div>
        <pre>[{
  "username": "u1",
  "email": "u1@example.com",
  "password": "Passw0rd!",
  "role": "user"
}, {
  "username": "u2",
  "email": "u2@example.com",
  "password": "Passw0rd!",
  "role": "manager"
}]</pre>
      </div>
      <a-textarea
        v-model="importForm.text"
        :auto-size="{ minRows: 6, maxRows: 10 }"
        placeholder="粘贴 JSON 数组"
      />
    </a-modal>
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
  color: var(--text-2);
  font-size: 13px;
  margin-top: 4px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar {
  padding: 12px;
}

.table :deep(.arco-select-view) {
  min-width: 120px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.import-tip {
  margin-bottom: 10px;
  color: var(--text-2);
  font-size: 13px;
}

.import-sample {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}

.import-sample-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 8px;
}

.import-sample pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-1);
}
</style>
