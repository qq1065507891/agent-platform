<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { createAgent } from '../../api/agents'
import { uploadKnowledge, type KnowledgeUploadResponse } from '../../api/knowledge'
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
  knowledgeFiles: [] as File[],
})

const uploadFileList = ref<any[]>([])
const uploading = ref(false)
const uploadResults = ref<KnowledgeUploadResponse[]>([])

const rules = {
  name: [{ required: true, message: '请输入名称' }],
  prompt_template: [{ required: true, message: '请输入提示词' }],
}

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const selectableSkillIds = computed(() =>
  new Set(skillOptions.value.filter((item) => item.status === 'active').map((item) => item.skill_id))
)

const getUnavailableSkillStatusLabel = (item: SkillItem) => {
  if (item.status === 'active') {
    return '可用'
  }

  if (item.source_type !== 'builtin' && !item.current_revision_id) {
    return '加载中'
  }

  if (item.source_type !== 'builtin' && item.current_revision_id) {
    return '审核失败/已禁用'
  }

  return '已禁用'
}

const selectOptions = computed(() => {
  return skillOptions.value
    .filter((item) => item && typeof item.skill_id === 'string' && typeof item.name === 'string')
    .map((item) => {
      const active = item.status === 'active'
      return {
        label: active
          ? `【可用】${item.name}`
          : `【不可用】${item.name}（${getUnavailableSkillStatusLabel(item)}）`,
        value: item.skill_id,
        disabled: !active,
      }
    })
    .sort((a, b) => {
      if (a.disabled !== b.disabled) return a.disabled ? 1 : -1
      return a.label.localeCompare(b.label, 'zh-CN')
    })
})

const fetchSkills = async () => {
  skillsLoading.value = true
  try {
    const pageSize = 100
    let page = 1
    let total = 0
    const all: SkillItem[] = []

    do {
      const data = await getSkills({ page, page_size: pageSize, status: 'active' })
      const list = Array.isArray(data?.list)
        ? data.list.filter((item: SkillItem) => item && typeof item.skill_id === 'string')
        : []
      total = Number(data?.total || 0)
      all.push(...list)
      page += 1
    } while ((page - 1) * pageSize < total && page <= 20)

    skillOptions.value = all
    form.skills = form.skills.filter((id) => selectableSkillIds.value.has(id))
  } catch (error: any) {
    Message.error(error?.message || '获取技能失败')
  } finally {
    skillsLoading.value = false
  }
}

const onFileChange = (fileList: any[] | undefined) => {
  if (!fileList?.length) {
    form.knowledgeFiles = []
    return
  }
  form.knowledgeFiles = fileList
    .map((item: any) => item.file as File | undefined)
    .filter((file: File | undefined): file is File => Boolean(file))
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.prompt_template = ''
  form.is_public = false
  form.skills = []
  form.knowledgeFiles = []
  uploadFileList.value = []
  uploadResults.value = []
}

const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const agent = await createAgent({
      name: form.name,
      description: form.description || undefined,
      prompt_template: form.prompt_template,
      is_public: form.is_public,
      skills: form.skills.map((skillId) => ({ skill_id: skillId })),
    })

    if (form.knowledgeFiles.length) {
      uploading.value = true
      const results = [] as KnowledgeUploadResponse[]
      for (const file of form.knowledgeFiles) {
        const result = await uploadKnowledge(file, agent.id)
        results.push(result)
      }
      uploadResults.value = results
      Message.success('知识库上传完成')
    }

    Message.success('智能体创建成功')
    emit('created')
    resetForm()
  } catch (error: any) {
    Message.error(error?.message || '创建失败')
  } finally {
    uploading.value = false
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
          :options="selectOptions"
          multiple
          allow-clear
          :max-tag-count="2"
        />
      </a-form-item>

      <a-form-item field="knowledgeFiles" label="专属知识库">
        <a-upload
          v-model:file-list="uploadFileList"
          :auto-upload="false"
          multiple
          :limit="5"
          accept=".pdf,.doc,.docx,.txt"
          @change="onFileChange"
        >
          <template #upload-button>
            <a-button type="outline">选择文件</a-button>
          </template>
        </a-upload>
        <div class="upload-tip">支持 PDF/DOC/DOCX/TXT，最多 5 个文件，创建后自动入库</div>
        <div v-if="form.knowledgeFiles.length" class="upload-list">
          <div v-for="file in form.knowledgeFiles" :key="file.name" class="upload-item">
            <span>{{ file.name }}</span>
          </div>
        </div>
        <div v-if="uploadResults.length" class="upload-result">
          <div v-for="item in uploadResults" :key="item.doc_id">
            文档 {{ item.doc_id }}：{{ item.chunk_count }} 段（v{{ item.version }}）
          </div>
        </div>
      </a-form-item>

      <a-form-item field="is_public" label="是否公开">
        <a-switch v-model="form.is_public" />
      </a-form-item>
    </a-form>

    <template #footer>
      <a-space>
        <a-button @click="drawerVisible = false">取消</a-button>
        <a-button type="primary" :loading="loading || uploading" @click="onSubmit">创建</a-button>
      </a-space>
    </template>
  </a-drawer>
</template>

<style scoped>
.upload-tip {
  margin-top: 8px;
  color: rgb(var(--gray-6));
  font-size: 12px;
}

.upload-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-item {
  color: rgb(var(--gray-8));
}

.upload-result {
  margin-top: 8px;
  color: rgb(var(--green-6));
  font-size: 12px;
}
</style>
