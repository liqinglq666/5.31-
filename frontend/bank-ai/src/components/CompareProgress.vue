<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  percent: number
  status: string
  processMode?: string
  isCancelling?: boolean
}>()

const emit = defineEmits<{
  cancel: []
  minimize: []
}>()

const modeMeta = computed(() => {
  if (props.processMode === 'RAG') {
    return {
      show: true,
      type: 'primary' as const,
      text: '🔍 深度 RAG 检索模式 (长文档优化)',
      pulse: true,
    }
  }
  if (props.processMode === 'DIRECT') {
    return {
      show: true,
      type: 'success' as const,
      text: '⚡ 标准全量比对模式',
      pulse: false,
    }
  }
  return { show: false, type: 'info' as const, text: '', pulse: false }
})
</script>

<template>
  <el-dialog
    :model-value="visible"
    width="460px"
    align-center
    :close-on-click-modal="false"
    :show-close="false"
  >
    <template #header>
      <div class="dialog-header">
        <span class="dialog-title">智能比对进度</span>
        <el-button
          text
          size="small"
          class="minimize-btn"
          @click="emit('minimize')"
        >
          最小化到后台
        </el-button>
      </div>
    </template>
    <div class="progress-body">
      <div v-if="modeMeta.show" class="mode-banner">
        <el-tag :type="modeMeta.type" effect="dark" size="large" class="mode-tag">
          {{ modeMeta.text }}
        </el-tag>
        <span v-if="modeMeta.pulse" class="pulse-dot" />
      </div>
      <el-progress
        :percentage="percent"
        :stroke-width="18"
        status=""
        striped
        striped-flow
      />
      <p class="progress-status">{{ status }}</p>
      <div class="cancel-row">
        <el-button
          type="danger"
          plain
          size="small"
          :loading="isCancelling"
          :disabled="percent >= 100"
          @click="emit('cancel')"
        >
          停止任务
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.dialog-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2129;
}

.minimize-btn {
  color: #86909c;
  font-size: 13px;
}

.minimize-btn:hover {
  color: #1e3a8a;
}

.progress-body {
  padding: 12px 8px;
  text-align: center;
}

.mode-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 18px;
}

.mode-tag {
  font-size: 13px;
  letter-spacing: 0.5px;
}

.progress-status {
  margin-top: 16px;
  font-size: 14px;
  color: #4b5563;
  min-height: 20px;
}

.cancel-row {
  margin-top: 18px;
  display: flex;
  justify-content: center;
}

/* 闪烁小圆点动画 */
.pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse-dot 1.4s infinite ease-in-out;
}

@keyframes pulse-dot {
  0% {
    transform: scale(0.6);
    opacity: 0.6;
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.45);
  }
  50% {
    transform: scale(1);
    opacity: 1;
    box-shadow: 0 0 0 8px rgba(59, 130, 246, 0);
  }
  100% {
    transform: scale(0.6);
    opacity: 0.6;
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
  }
}
</style>
