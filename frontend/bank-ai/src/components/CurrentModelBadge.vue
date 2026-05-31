<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Cpu } from '@element-plus/icons-vue'
import { getActiveModel } from '@/api/system'
import type { ActiveModelInfo } from '@/types/api'

const activeModel = ref<ActiveModelInfo | null>(null)
let intervalId: number | null = null

const fetchActive = async () => {
  try {
    const res = await getActiveModel()
    if (res.data.code === 200) {
      activeModel.value = res.data.data
    }
  } catch (_err) {
    // 静默失败，不阻断 UI
  }
}

onMounted(() => {
  fetchActive()
  intervalId = window.setInterval(fetchActive, 30000)
})

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<template>
  <div v-if="activeModel" class="current-model-badge">
    <el-icon :size="14"><Cpu /></el-icon>
    <span class="model-label">当前模型</span>
    <el-tag size="small" type="primary" effect="light">
      {{ activeModel.model_name }}
    </el-tag>
  </div>
</template>

<style scoped>
.current-model-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #4e5969;
  background: #f7f8fa;
  padding: 4px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.model-label {
  font-weight: 500;
  color: #86909c;
}
</style>
