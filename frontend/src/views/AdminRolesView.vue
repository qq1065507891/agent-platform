<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getRoles } from '../api/roles'
import { getApiErrorMessage } from '../utils/request'

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
  } catch (error: unknown) {
    Message.error(getApiErrorMessage(error, '获取角色失败'))
  } finally {
    loading.value = false
  }
}

const formatPermissions = (permissions: string[]) => permissions.join(', ')

onMounted(fetchRoles)
</script>

<template>
  <div class="admin-page">
    <section class="hero glass-panel">
      <div>
        <div class="title">角色管理</div>
        <div class="subtitle">查看角色权限清单</div>
      </div>
    </section>

    <a-table class="table"
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
  background-image: linear-gradient(135deg, rgba(109, 94, 248, 0.22), rgba(79, 140, 255, 0.12));
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

.table {
  border-radius: 14px;
  overflow: hidden;
}
</style>
