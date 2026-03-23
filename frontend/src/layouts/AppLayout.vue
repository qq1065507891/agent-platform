<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const selectedKey = computed(() => {
  if (route.path.startsWith('/admin/users')) return 'admin-users'
  if (route.path.startsWith('/admin/roles')) return 'admin-roles'
  if (route.path.startsWith('/admin/skills')) return 'admin-skills'
  if (route.path.startsWith('/admin/agents')) return 'admin-agents'
  if (route.path.startsWith('/admin/dashboard')) return 'admin-dashboard'
  if (route.path.startsWith('/chat')) return 'chat'
  if (route.path.startsWith('/my-agents')) return 'my-agents'
  if (route.path.startsWith('/agents')) return 'agents'
  return 'agents'
})

const onMenuClick = (key: string) => {
  if (key === 'agents') {
    router.push('/agents')
  }
  if (key === 'my-agents') {
    router.push('/my-agents')
  }
  if (key === 'chat') {
    router.push('/chat/placeholder')
  }
  if (key === 'admin-users') {
    router.push('/admin/users')
  }
  if (key === 'admin-roles') {
    router.push('/admin/roles')
  }
  if (key === 'admin-skills') {
    router.push('/admin/skills')
  }
  if (key === 'admin-agents') {
    router.push('/admin/agents')
  }
  if (key === 'admin-dashboard') {
    router.push('/admin/dashboard')
  }
}

const onLogout = () => {
  authStore.clearAuth()
  router.push('/login')
}
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header">
      <div class="logo">Agent 平台</div>
      <div class="header-actions">
        <span class="user-name">{{ authStore.user?.username ?? '未登录' }}</span>
        <a-button type="primary" status="warning" size="small" @click="onLogout">登出</a-button>
      </div>
    </a-layout-header>

    <a-layout>
      <a-layout-sider class="app-sider" :width="220">
        <a-menu :selected-keys="[selectedKey]" @menu-item-click="onMenuClick">
          <a-menu-item key="agents">智能体市场</a-menu-item>
          <a-menu-item key="my-agents">我的智能体</a-menu-item>
          <a-menu-item key="chat">我的会话</a-menu-item>
          <a-sub-menu v-if="authStore.user?.role === 'admin'" key="admin">
            <template #title>系统管理</template>
            <a-menu-item key="admin-users">用户管理</a-menu-item>
            <a-menu-item key="admin-roles">角色管理</a-menu-item>
            <a-menu-item key="admin-skills">技能管理</a-menu-item>
            <a-menu-item key="admin-agents">智能体管理</a-menu-item>
            <a-menu-item key="admin-dashboard">数据看板</a-menu-item>
          </a-sub-menu>
        </a-menu>
      </a-layout-sider>

      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: #f5f6f8;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #1f2937;
  color: #fff;
}

.logo {
  font-size: 18px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  font-size: 14px;
}

.app-sider {
  background: #fff;
  border-right: 1px solid #e5e6eb;
}

.app-content {
  padding: 24px;
  min-height: calc(100vh - 64px);
}
</style>
