<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { createAgent } from '../../api/agents'
import { getSkills, type SkillItem } from '../../api/skills'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits(['update:visible', 'created'])

const formRef = ref()
const loading = ref(false)
const skillsLoading = ref(false)
const skillOptions = ref<SkillItem[]>([])

const form = reactive({
  name: '',
  description: '',
  prompt_template: '',
  is_public: false,
  skills: [] as string[],
})

const rules = {
  name: [{ required: true, message: '请输入名称' }],
  prompt_template: [{ required: true, message: '请输入提示词' }],
}

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const fetchSkills = async () => {
  skillsLoading.value = true
  try {
    const data = await getSkills({ page: 1, page_size: 100, status: 'active' })
    skillOptions.value = data.list
  } catch (error: any) {
    Message.error(error?.message || '获取技能失败')
  } finally {
    skillsLoading.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.prompt_template = ''
  form.is_public = false
  form.skills = []
}

const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch (error) {
    return
  }
  loading.value = true
  try {
    await createAgent({
      name: form.name,
      description: form.description || undefined,
      prompt_template: form.prompt_template,
      is_public: form.is_public,
      skills: form.skills.map((skillId) => ({ skill_id: skillId })),
    })
    Message.success('智能体创建成功')
    emit('created')
    resetForm()
  } catch (error: any) {
    Message.error(error?.message || '创建失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      fetchSkills()
    }
  }
)

onMounted(fetchSkills)
</script>

<template>
  <a-drawer v-model:visible="drawerVisible" width="540" title="创建智能体" :mask-closable="false">
    <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
      <a-form-item field="name" label="名称" required>
        <a-input v-model="form.name" placeholder="请输入智能体名称" />
      </a-form-item>

      <a-form-item field="description" label="描述">
        <a-textarea v-model="form.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
      </a-form-item>

      <a-form-item field="prompt_template" label="提示词" required>
        <a-textarea
          v-model="form.prompt_template"
          :auto-size="{ minRows: 6, maxRows: 10 }"
          placeholder="请输入 Prompt Template"
        />
      </a-form-item>

      <a-form-item field="skills" label="技能绑定">
        <a-select
          v-model="form.skills"
          placeholder="请选择技能"
          :loading="skillsLoading"
          :options="skillOptions.map((item) => ({ label: item.name, value: item.skill_id }))"
          multiple
          allow-clear
        />
      </a-form-item>

      <a-form-item field="is_public" label="是否公开">
        <a-switch v-model="form.is_public" />
      </a-form-item>
    </a-form>

    <template #footer>
      <a-space>
        <a-button @click="drawerVisible = false">取消</a-button>
        <a-button type="primary" :loading="loading" @click="onSubmit">创建</a-button>
      </a-space>
    </template>
  </a-drawer>
</template>
