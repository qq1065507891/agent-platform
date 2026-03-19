<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { createUser, getUsers, importUsers, updateUser } from '../api/users'
import { getRoles } from '../api/roles'

interface UserRow {
  id?: string
  _rowKey?: string
  username: string
  email: string
  role: string
  status: 'active' | 'disabled'
  created_at?: string
}

const buildRowKey = (item: UserRow) => item.id || item._rowKey || `${item.username}-${item.email}`

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
  } catch (error: any) {
    Message.error(error?.message || '获取角色失败')
  }
}

const fetchUsers = async () => {
  loading.value = true
  try {
    const data = await getUsers({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: keyword.value || undefined,
    })
    const list = Array.isArray(data?.list)
      ? data.list
      : Array.isArray(data?.data?.list)
        ? data.data.list
        : []
    users.value = list.map((item: UserRow) => normalizeRow(item))
    tableData.value = users.value
    pagination.total = data?.total ?? data?.data?.total ?? 0
  } catch (error: any) {
    Message.error(error?.message || '获取用户失败')
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

const onStatusChange = async (row: UserRow, status: 'active' | 'disabled') => {
  try {
    await updateUser(row.id, { status })
    row.status = status
    Message.success('状态已更新')
  } catch (error: any) {
    Message.error(error?.message || '更新失败')
  }
}

const onRoleChange = async (row: UserRow, role: string) => {
  try {
    await updateUser(row.id, { role })
    row.role = role
    Message.success('角色已更新')
  } catch (error: any) {
    Message.error(error?.message || '更新失败')
  }
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
  } catch (error: any) {
    Message.error(error?.message || '创建失败')
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
  } catch (error: any) {
    Message.error(error?.message || '导入失败')
  }
}

onMounted(() => {
  fetchRoles()
  fetchUsers()
})
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <div class="title">用户管理</div>
        <div class="subtitle">管理用户角色与状态</div>
      </div>
      <div class="actions">
        <a-input-search
          v-model="keyword"
          placeholder="搜索用户名/邮箱"
          allow-clear
          @search="onSearch"
        />
        <a-button type="primary" @click="createVisible = true">新增用户</a-button>
        <a-button type="outline" @click="importVisible = true">批量导入</a-button>
      </div>
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
          @change="(value) => onRoleChange(record, String(value))"
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
          @change="(value) => onStatusChange(record, value as 'active' | 'disabled')"
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

.table :deep(.arco-table-header) {
  background: #f8fafc;
}

.table :deep(.arco-table-td) {
  color: #111827;
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
  color: #4b5563;
  font-size: 13px;
}

.import-sample {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}

.import-sample-title {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.import-sample pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: #0f172a;
}
</style>
