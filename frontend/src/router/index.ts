import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import AgentsView from '../views/AgentsView.vue'
import ChatView from '../views/ChatView.vue'
import AppLayout from '../layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/agents' },
      { path: 'agents', name: 'agents', component: AgentsView },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/AdminDashboardView.vue') },
      { path: 'my-agents', name: 'my-agents', component: () => import('../views/MyAgentsView.vue') },
      { path: 'my-agents/create', name: 'agent-create', component: () => import('../views/AgentCreateView.vue') },
      { path: 'my-agents/:id/edit', name: 'agent-edit', component: () => import('../views/AgentEditView.vue') },
      { path: 'chat/:id', name: 'chat', component: ChatView },
      { path: 'agent-chat/:agentId', name: 'agent-chat', component: () => import('../views/AgentChatView.vue') },
      {
        path: 'admin/users',
        name: 'admin-users',
        component: () => import('../views/AdminUsersView.vue'),
        meta: { requireAdmin: true },
      },
      {
        path: 'admin/roles',
        name: 'admin-roles',
        component: () => import('../views/AdminRolesView.vue'),
        meta: { requireAdmin: true },
      },
      {
        path: 'admin/skills',
        name: 'admin-skills',
        component: () => import('../views/AdminSkillsView.vue'),
        meta: { requireAdmin: true },
      },
      {
        path: 'admin/mcp-tools',
        name: 'admin-mcp-tools',
        component: () => import('../views/AdminMcpToolsView.vue'),
        meta: { requireAdmin: true },
      },
      {
        path: 'admin/agents',
        name: 'admin-agents',
        component: () => import('../views/AdminAgentsView.vue'),
        meta: { requireAdmin: true },
      },
      {
        path: 'admin/dashboard',
        name: 'admin-dashboard',
        component: () => import('../views/AdminDashboardView.vue'),
        meta: { requireAdmin: true },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/agents' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const getCurrentUser = () => {
  const raw = localStorage.getItem('user')
  if (!raw) return null

  try {
    return JSON.parse(raw)
  } catch {
    localStorage.removeItem('user')
    return null
  }
}

router.beforeEach((to) => {
  if (to.meta.public) {
    return true
  }

  const token = localStorage.getItem('access_token')
  if (!token) {
    return '/login'
  }

  const user = getCurrentUser()

  if (to.meta.requireAdmin && (!user || user.role !== 'admin')) {
    return '/agents'
  }

  if (to.path === '/admin/dashboard' && (!user || user.role !== 'admin')) {
    return '/dashboard'
  }

  return true
})

export default router
