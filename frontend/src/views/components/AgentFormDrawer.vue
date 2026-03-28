<script setup lang="ts">
import { computed } from 'vue'
import AgentFormPanel from './AgentFormPanel.vue'

interface AgentBinding {
  skill_id: string
  type?: string
}

interface AgentEditable {
  id: string
  name: string
  description?: string
  prompt_template: string
  is_public?: boolean
  skills?: AgentBinding[]
}

const props = defineProps<{ visible: boolean; mode?: 'create' | 'edit'; agent?: AgentEditable | null }>()
const emit = defineEmits(['update:visible', 'created', 'updated'])

const currentMode = computed(() => props.mode || 'create')
const drawerTitle = computed(() => (currentMode.value === 'edit' ? '编辑智能体' : '创建智能体'))

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const onSaved = () => {
  if (currentMode.value === 'edit') {
    emit('updated')
  } else {
    emit('created')
  }
  drawerVisible.value = false
}
</script>

<template>
  <a-drawer
    v-model:visible="drawerVisible"
    width="720"
    :title="drawerTitle"
    :mask-closable="false"
    :teleport="false"
  >
    <agent-form-panel :mode="currentMode" :agent="agent" @saved="onSaved" @cancel="drawerVisible = false" />
  </a-drawer>
</template>
