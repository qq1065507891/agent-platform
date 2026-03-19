<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getRoles } from '../api/roles'

interface RoleRow {
  id?: string
  _rowKey?: string
  name: string
  permissions: string[]
}

const loading = ref(false)
const roles = ref<RoleRow[]>([])

const normalizeRow = (item: RoleRow): RoleRow => ({
  ...item,
  _rowKey: item.id || item._rowKey || item.name,
})

const safeRoles = computed(() => (Array.isArray(roles.value) ? [...roles.value] : []))

const columns = [
  { title: '角色名称', dataIndex: 'name' },
  { title: '权限标识', dataIndex: 'permissions', slotName: 'permissions' },
]

const fetchRoles = async () => {
  loading.value = true
  try {
    const data = await getRoles()
    const list = Array.isArray(data) ? data : data?.list
    roles.value = (list || []).map((item: RoleRow) => normalizeRow(item))
  } catch (error: any) {
    Message.error(error?.message || '获取角色失败')
  } finally {
    loading.value = false
  }
}

const formatPermissions = (permissions: string[]) => permissions.join(', ')

onMounted(fetchRoles)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <div class="title">角色管理</div>
        <div class="subtitle">查看角色权限清单</div>
      </div>
    </div>

    <a-table
      :data="safeRoles"
      :columns="columns"
      :pagination="false"
      :loading="loading"
      row-key="_rowKey"
      :bordered="true"
      :scroll="{ x: 700 }"
    >
      <template #permissions="{ record }">
        <span>{{ formatPermissions(record.permissions) || '-' }}</span>
      </template>
    </a-table>
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
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.subtitle {
  color: #6b7280;
  font-size: 12px;
}
</style>
