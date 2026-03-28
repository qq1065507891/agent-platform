<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useAuthStore } from '../stores/auth'
import { login } from '../api/auth'
import { getApiErrorMessage } from '../utils/request'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const onSubmit = async () => {
  if (!form.username || !form.password) {
    Message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const data = await login({
      username: form.username,
      password: form.password,
      login_type: 'password',
    })
    authStore.setAuth(data.access_token, data.user)
    Message.success('登录成功')
    router.push('/agents')
  } catch (error: any) {
    Message.error(getApiErrorMessage(error, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="title">Agent 平台登录</div>
      <div class="subtitle">欢迎回来，请使用账号密码登录</div>
      <a-form :model="form" layout="vertical" @submit.prevent="onSubmit">
        <a-form-item field="username" label="用户名">
          <a-input v-model="form.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item field="password" label="密码">
          <a-input-password v-model="form.password" placeholder="请输入密码" />
        </a-form-item>
        <a-button html-type="submit" type="primary" long :loading="loading" @click="onSubmit">登录</a-button>
      </a-form>

      <div class="footer-link">
        还没有账号？
        <a-link @click="router.push('/register')">去注册</a-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2937, #0f172a);
}

.login-card {
  width: 380px;
  background: #fff;
  padding: 32px;
  border-radius: 16px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.2);
}

.title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #111827 !important;
}

.subtitle {
  font-size: 13px;
  color: #374151 !important;
  margin-bottom: 18px;
}

.footer-link {
  margin-top: 14px;
  text-align: center;
  color: #374151;
}

.login-card,
.login-card * {
  color: #111827 !important;
}

:deep(.arco-form-item-label-col > label) {
  color: #111827 !important;
}

:deep(.arco-input-wrapper),
:deep(.arco-textarea-wrapper),
:deep(.arco-input-password) {
  background: #ffffff !important;
  border-color: #d1d5db !important;
  color: #111827 !important;
}

:deep(.arco-input),
:deep(.arco-input-inner),
:deep(input) {
  color: #111827 !important;
}

:deep(.arco-input::placeholder),
:deep(input::placeholder) {
  color: #9ca3af !important;
}
</style>
