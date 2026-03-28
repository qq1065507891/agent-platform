<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { logout } from '../api/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const selectedKey = computed(() => {
  if (route.path.startsWith('/admin/users')) return 'admin-users'
  if (route.path.startsWith('/admin/roles')) return 'admin-roles'
  if (route.path.startsWith('/admin/skills')) return 'admin-skills'
  if (route.path.startsWith('/admin/mcp-tools')) return 'admin-mcp-tools'
  if (route.path.startsWith('/admin/agents')) return 'admin-agents'
  if (route.path.startsWith('/admin/dashboard')) return 'admin-dashboard'
  if (route.path.startsWith('/dashboard')) return 'dashboard'
  if (route.path.startsWith('/chat')) return 'chat'
  if (route.path.startsWith('/my-agents')) return 'my-agents'
  if (route.path.startsWith('/agents')) return 'agents'
  return 'agents'
})

const currentSectionTitle = computed(() => {
  const map: Record<string, string> = {
    agents: '智能体市场',
    'my-agents': '我的智能体',
    chat: '我的会话',
    dashboard: '数据看板',
    'admin-users': '用户管理',
    'admin-roles': '角色管理',
    'admin-skills': '技能管理',
    'admin-mcp-tools': 'MCP 工具管理',
    'admin-agents': '智能体管理',
    'admin-dashboard': '管理看板',
  }
  return map[selectedKey.value] || '智能体平台'
})

const onMenuClick = (key: string) => {
  if (key === 'agents') {
    router.push('/agents')
  }
  if (key === 'my-agents') {
    router.push('/my-agents')
  }
  if (key === 'dashboard') {
    router.push('/dashboard')
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
  if (key === 'admin-mcp-tools') {
    router.push('/admin/mcp-tools')
  }
  if (key === 'admin-agents') {
    router.push('/admin/agents')
  }
  if (key === 'admin-dashboard') {
    router.push('/admin/dashboard')
  }
}

const onLogout = async () => {
  try {
    await logout()
  } catch {
    // ignore logout API errors and clear local auth anyway
  }
  authStore.clearAuth()
  router.push('/login')
}
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header glass-panel">
      <div class="header-left">
        <div class="logo-wrap">
          <div class="logo-dot"></div>
          <div class="logo">Agent 平台</div>
        </div>
        <div class="current-title">{{ currentSectionTitle }}</div>
      </div>

      <div class="header-actions">
        <div class="user-chip">
          <span class="user-name">{{ authStore.user?.username ?? '未登录' }}</span>
        </div>
        <a-button type="primary" status="warning" size="small" @click="onLogout">登出</a-button>
      </div>
    </a-layout-header>

    <a-layout class="main-shell">
      <a-layout-sider class="app-sider glass-panel" :width="250">
        <div class="menu-group-title">核心功能</div>
        <a-menu class="brand-menu" :selected-keys="[selectedKey]" @menu-item-click="onMenuClick">
          <a-menu-item key="agents">智能体市场</a-menu-item>
          <a-menu-item key="my-agents">我的智能体</a-menu-item>
          <a-menu-item key="chat">我的会话</a-menu-item>
          <a-menu-item key="dashboard">数据看板</a-menu-item>

          <a-sub-menu v-if="authStore.user?.role === 'admin'" key="admin">
            <template #title>
              <span class="menu-group-title nested">系统管理</span>
            </template>
            <a-menu-item key="admin-users">用户管理</a-menu-item>
            <a-menu-item key="admin-roles">角色管理</a-menu-item>
            <a-menu-item key="admin-skills">技能管理</a-menu-item>
            <a-menu-item key="admin-mcp-tools">MCP工具管理</a-menu-item>
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
  background: transparent;
}

.main-shell {
  padding: 12px 14px 14px;
  background: transparent;
}

.glass-panel {
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
}

.app-header {
  margin: 10px 14px 0;
  border-radius: var(--radius-xl);
  height: 74px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 18px;
}

.logo-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--brand-1), var(--accent));
  box-shadow: 0 0 14px rgba(109, 94, 248, 0.95);
}

.logo {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--text-1);
}

.current-title {
  color: var(--text-2);
  font-size: 13px;
}

.header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.user-chip {
  height: 30px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.08);
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
}

.user-name {
  font-size: 13px;
  color: var(--text-1);
}

.app-sider {
  border-radius: var(--radius-xl);
  margin-right: 14px;
  padding: 14px 10px;
}

.menu-group-title {
  color: #ffffff;
  font-size: 12px;
  padding: 4px 8px 8px;
  letter-spacing: 0.2px;
}

.menu-group-title.nested {
  padding: 0;
}

.brand-menu {
  background: transparent;
  border: none;
}

.app-content {
  border-radius: var(--radius-xl);
  min-height: calc(100vh - 112px);
}

:deep(.brand-menu .arco-menu-inner) {
  background: transparent;
}

:deep(.brand-menu .arco-menu-item),
:deep(.brand-menu .arco-menu-inline-header) {
  border-radius: 10px;
  margin: 3px 0;
  color: var(--text-2);
  background: rgba(11, 19, 46, 0.28);
}

:deep(.brand-menu .arco-menu-item:hover),
:deep(.brand-menu .arco-menu-inline-header:hover) {
  background: rgba(24, 36, 78, 0.62);
  color: var(--text-1);
}

:deep(.brand-menu .arco-menu-selected) {
  background: linear-gradient(135deg, rgba(109, 94, 248, 0.42), rgba(79, 140, 255, 0.3));
  color: #fff;
  box-shadow: 0 10px 22px rgba(79, 140, 255, 0.24);
}

:deep(.arco-layout-sider-children) {
  overflow: auto;
}

:deep(.arco-input-wrapper),
:deep(.arco-input-search),
:deep(.arco-textarea-wrapper) {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.16);
  color: var(--text-1);
}

:deep(.arco-input-wrapper:hover),
:deep(.arco-textarea-wrapper:hover) {
  border-color: rgba(255, 255, 255, 0.3);
}

:deep(.arco-btn-primary) {
  background: linear-gradient(135deg, var(--brand-1), var(--brand-2));
  border-color: transparent;
}

:deep(.arco-btn-primary:hover) {
  filter: brightness(1.1);
}

@media (max-width: 900px) {
  .app-header {
    height: auto;
    padding: 12px;
    gap: 10px;
    flex-direction: column;
    align-items: stretch;
  }

  .header-left,
  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .main-shell {
    padding: 10px;
  }

  .app-sider {
    width: 200px !important;
    min-width: 200px !important;
    margin-right: 10px;
  }
}

@media (max-width: 700px) {
  .main-shell {
    flex-direction: column;
  }

  .app-sider {
    width: 100% !important;
    min-width: 100% !important;
    margin-right: 0;
    margin-bottom: 10px;
  }

  .current-title {
    display: none;
  }
}
</style>
