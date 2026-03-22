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
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/agents' },
      { path: 'agents', name: 'agents', component: AgentsView },
      { path: 'my-agents', name: 'my-agents', component: () => import('../views/MyAgentsView.vue') },
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
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/agents' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  if (to.meta.public) {
    next()
    return
  }
  const token = localStorage.getItem('access_token')
  if (!token) {
    next('/login')
    return
  }
  if (to.meta.requireAdmin) {
    const raw = localStorage.getItem('user')
    const user = raw ? JSON.parse(raw) : null
    if (!user || user.role !== 'admin') {
      next('/agents')
      return
    }
  }
  next()
})

export default router
