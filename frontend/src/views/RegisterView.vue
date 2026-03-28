<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { register } from '../api/auth'
import { getApiErrorMessage } from '../utils/request'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const onSubmit = async () => {
  if (!form.username || !form.email || !form.password || !form.confirmPassword) {
    Message.warning('请完整填写注册信息')
    return
  }

  if (form.password !== form.confirmPassword) {
    Message.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    await register({
      username: form.username,
      email: form.email,
      password: form.password,
    })
    Message.success('注册成功，请登录')
    router.push('/login')
  } catch (error: any) {
    Message.error(getApiErrorMessage(error, '注册失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-card">
      <div class="title">创建账号</div>
      <div class="subtitle">注册后可直接登录 Agent 平台</div>
      <a-form :model="form" layout="vertical" @submit.prevent="onSubmit">
        <a-form-item field="username" label="用户名">
          <a-input v-model="form.username" placeholder="3-32位，字母/数字/下划线" />
        </a-form-item>
        <a-form-item field="email" label="邮箱">
          <a-input v-model="form.email" placeholder="请输入邮箱" />
        </a-form-item>
        <a-form-item field="password" label="密码">
          <a-input-password v-model="form.password" placeholder="8-32位，需包含字母和数字" />
        </a-form-item>
        <a-form-item field="confirmPassword" label="确认密码">
          <a-input-password v-model="form.confirmPassword" placeholder="请再次输入密码" />
        </a-form-item>
        <a-button html-type="submit" type="primary" long :loading="loading" @click="onSubmit">注册</a-button>
      </a-form>

      <div class="footer-link">
        已有账号？
        <a-link @click="router.push('/login')">去登录</a-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2937, #0f172a);
}

.register-card {
  width: 420px;
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

.register-card,
.register-card * {
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
