<script setup lang="ts">
import { computed } from 'vue'
import { Document, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import type { BatchExportItem } from '@/composables/useBatchPdfExport'

const props = defineProps<{
  visible: boolean
  items: BatchExportItem[]
  currentIndex: number
  isRunning: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'cancel'): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const total = computed(() => props.items.length)
const successCount = computed(() => props.items.filter((i) => i.status === 'success').length)
const errorCount = computed(() => props.items.filter((i) => i.status === 'error').length)
const progressPercent = computed(() => {
  if (total.value === 0) return 0
  return Math.round(((props.currentIndex + 1) / total.value) * 100)
})

const statusIcon = (status: string) => {
  switch (status) {
    case 'success':
      return CircleCheck
    case 'error':
      return CircleClose
    case 'processing':
      return Loading
    default:
      return Document
  }
}

const statusType = (status: string) => {
  switch (status) {
    case 'success':
      return 'success'
    case 'error':
      return 'danger'
    case 'processing':
      return 'primary'
    default:
      return 'info'
  }
}

const handleCancel = () => {
  emit('cancel')
}

const handleClose = () => {
  if (!props.isRunning) {
    dialogVisible.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="批量导出 PDF"
    width="560px"
    :close-on-click-modal="!isRunning"
    :close-on-press-escape="!isRunning"
    :show-close="!isRunning"
    align-center
    destroy-on-close
  >
    <div class="batch-export-modal">
      <!-- 总体进度 -->
      <div class="overall-progress">
        <div class="progress-header">
          <span class="progress-title">总体进度</span>
          <span class="progress-count">
            {{ currentIndex + 1 > total ? total : currentIndex + 1 }} / {{ total }}
          </span>
        </div>
        <el-progress
          :percentage="progressPercent"
          :status="isRunning ? '' : errorCount > 0 ? 'exception' : 'success'"
          :stroke-width="10"
        />
        <div class="progress-stats">
          <el-tag type="success" size="small">成功 {{ successCount }}</el-tag>
          <el-tag v-if="errorCount > 0" type="danger" size="small">失败 {{ errorCount }}</el-tag>
          <el-tag v-if="isRunning" type="primary" size="small">进行中</el-tag>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="task-list">
        <div
          v-for="(item, idx) in items"
          :key="item.record.task_id"
          class="task-item"
          :class="{ 'task-item--active': idx === currentIndex }"
        >
          <el-icon class="task-icon" :class="`task-icon--${item.status}`">
            <component :is="statusIcon(item.status)" />
          </el-icon>
          <div class="task-info">
            <div class="task-name">{{ item.record.project_name || item.record.task_id }}</div>
            <div v-if="item.message" class="task-message">{{ item.message }}</div>
          </div>
          <el-tag
            :type="statusType(item.status)"
            size="small"
            effect="plain"
            class="task-status"
          >
            {{
              item.status === 'pending'
                ? '等待中'
                : item.status === 'processing'
                  ? '生成中'
                  : item.status === 'success'
                    ? '已完成'
                    : '失败'
            }}
          </el-tag>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button v-if="isRunning" type="danger" @click="handleCancel">
        取消导出
      </el-button>
      <el-button v-else type="primary" @click="handleClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch-export-modal {
  max-height: 420px;
  overflow-y: auto;
}

.overall-progress {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.progress-count {
  font-size: 13px;
  color: #64748b;
}

.progress-stats {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  transition: background-color 0.2s ease;
}

.task-item--active {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.task-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.task-icon--success {
  color: #10b981;
}

.task-icon--error {
  color: #ef4444;
}

.task-icon--processing {
  color: #3b82f6;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.task-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-name {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-message {
  font-size: 11px;
  color: #ef4444;
}

.task-status {
  flex-shrink: 0;
}
</style>
