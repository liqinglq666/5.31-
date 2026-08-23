<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { Cpu } from '@element-plus/icons-vue'
import { useModelStore } from '@/store/model'

const props = defineProps<{
  modelValue: string
  size?: 'default' | 'small' | 'large'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const modelStore = useModelStore()

onMounted(() => {
  if (modelStore.models.length === 0) {
    modelStore.fetchModels()
  }
})

const selectedModel = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
</script>

<template>
  <div class="model-selector">
    <el-select
      v-model="selectedModel"
      :size="size || 'default'"
      placeholder="选择 AI 模型"
      class="model-select"
      :loading="modelStore.loading"
    >
      <template #prefix>
        <el-icon><Cpu /></el-icon>
      </template>

      <el-option-group
        v-for="group in modelStore.groupedModels"
        :key="group.provider"
        :label="group.provider"
      >
        <el-option
          v-for="model in group.models"
          :key="model.id"
          :label="model.name"
          :value="model.id"
        >
          <div class="model-option">
            <span class="model-name">{{ model.name }}</span>
            <div class="model-meta">
              <el-tag v-if="model.recommended" type="danger" size="small" effect="dark">
                推荐
              </el-tag>
              <span v-if="model.version" class="model-version">{{ model.version }}</span>
            </div>
          </div>
        </el-option>
      </el-option-group>

      <template #empty>
        <el-empty description="暂无可用模型" :image-size="60" />
      </template>
    </el-select>
  </div>
</template>

<style scoped>
.model-selector {
  width: 100%;
}

.model-select {
  width: 100%;
}

.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
}

.model-name {
  font-size: 14px;
  color: #1d2129;
}

.model-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-version {
  font-size: 12px;
  color: #86909c;
}
</style>
