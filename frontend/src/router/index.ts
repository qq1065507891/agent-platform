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
  next()
})

export default router
