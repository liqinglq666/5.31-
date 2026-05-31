<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { View, RefreshRight, CircleClose, Loading, InfoFilled } from '@element-plus/icons-vue'
import { useCompareStore } from '@/store/compare'
import { useUserStore } from '@/store'
import type { RunningTask } from '@/types/api'

const compareStore = useCompareStore()
const userStore = useUserStore()
const router = useRouter()

const emit = defineEmits<{
  (e: 'viewResult'): void
}>()

const activeTab = ref('active')

const statusTagType = (status: string) => {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'cancelled':
      return 'info'
    case 'processing':
      return 'primary'
    default:
      return 'warning'
  }
}

const statusTagText = (status: string) => {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    case 'processing':
      return '处理中'
    case 'pending':
      return '等待中'
    default:
      return status
  }
}

const handleShowProgress = (task: RunningTask) => {
  compareStore.showTaskProgress(task.taskId)
}

const handleCancel = async (task: RunningTask) => {
  await compareStore.cancelTask(task.taskId)
}

const handleRetry = async (task: RunningTask) => {
  await compareStore.retryTask(task.taskId)
}

const handleViewResult = async (task: RunningTask) => {
  const ok = await compareStore.loadTaskResult(task.taskId)
  if (ok) {
    emit('viewResult')
    ElMessage.success('已加载比对结果')
  } else {
    ElMessage.warning('暂无比对结果')
  }
}

const rowClassName = ({ row }: { row: RunningTask }) => {
  if (row.status === 'failed') return 'row-failed'
  return ''
}
</script>

<template>
  <div class="task-center-view">
    <!-- 游客模式提示 -->
    <div v-if="userStore.isGuest" class="guest-banner">
      <el-icon><Info-Filled /></el-icon>
      <span>您正在以游客身份浏览，仅展示最近 10 条已完成的比对记录。如需上传比对，请注册登录。</span>
    </div>

    <div class="task-center-header">
      <h2>任务中心</h2>
      <p>管理您的比对任务队列，支持后台运行与进度追踪</p>
    </div>

    <el-tabs v-model="activeTab" type="border-card" class="task-tabs">
      <!-- 进行中 -->
      <el-tab-pane label="进行中" name="active">
        <el-empty
          v-if="compareStore.activeTasks.length === 0"
          description="暂无进行中的比对任务"
        />

        <el-table
          v-else
          :data="compareStore.activeTasks"
          style="width: 100%"
          :row-class-name="rowClassName"
        >
          <el-table-column label="比对文件" min-width="220">
            <template #default="{ row }">
              <div class="file-cell">
                <span class="file-name">{{ row.fileName }}</span>
                <el-tag
                  v-if="row.batchInfo"
                  size="small"
                  type="info"
                  class="batch-tag"
                >
                  队列 {{ row.batchInfo.current }}/{{ row.batchInfo.total }}
                </el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="进度" width="200">
            <template #default="{ row }">
              <el-progress
                :percentage="row.progress"
                :status="row.status === 'failed' ? 'exception' : ''"
                striped
                :striped-flow="row.status === 'processing'"
              />
            </template>
          </el-table-column>

          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusTagText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="当前阶段" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.message }}
            </template>
          </el-table-column>

          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                :icon="View"
                @click="handleShowProgress(row)"
              >
                查看
              </el-button>
              <el-button
                size="small"
                type="danger"
                :icon="CircleClose"
                :loading="row.isCancelling"
                @click="handleCancel(row)"
              >
                取消
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 最近完成 -->
      <el-tab-pane label="最近完成" name="recent">
        <el-empty
          v-if="compareStore.recentTasks.length === 0"
          description="暂无最近完成的任务"
        />

        <!-- 桌面端：表格 -->
        <el-table
          v-else
          :data="compareStore.recentTasks"
          style="width: 100%"
          :row-class-name="rowClassName"
          class="desktop-table"
        >
          <el-table-column label="比对文件" min-width="220">
            <template #default="{ row }">
              <div class="file-cell">
                <span class="file-name">{{ row.fileName }}</span>
                <el-tag
                  v-if="row.batchInfo"
                  size="small"
                  type="info"
                  class="batch-tag"
                >
                  队列 {{ row.batchInfo.current }}/{{ row.batchInfo.total }}
                </el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="结果" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusTagText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="结束时间" width="160">
            <template #default="{ row }">
              {{ new Date(row.startTime).toLocaleString() }}
            </template>
          </el-table-column>

          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'completed'"
                size="small"
                type="primary"
                :icon="View"
                @click="handleViewResult(row)"
              >
                查看结果
              </el-button>
              <el-button
                v-if="row.status === 'failed'"
                size="small"
                type="warning"
                :icon="RefreshRight"
                @click="handleRetry(row)"
              >
                重试
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 手机端：卡片列表 -->
        <div v-if="compareStore.recentTasks.length > 0" class="mobile-card-list">
          <div
            v-for="task in compareStore.recentTasks"
            :key="task.taskId"
            class="task-card"
            :class="{ 'task-card--failed': task.status === 'failed' }"
          >
            <div class="task-card-header">
              <span class="task-card-name">{{ task.fileName }}</span>
              <el-tag :type="statusTagType(task.status)" size="small">
                {{ statusTagText(task.status) }}
              </el-tag>
            </div>
            <div class="task-card-time">
              {{ new Date(task.startTime).toLocaleString() }}
            </div>
            <div class="task-card-actions">
              <el-button
                v-if="task.status === 'completed'"
                size="small"
                type="primary"
                @click="handleViewResult(task)"
              >
                <el-icon><View /></el-icon>
                查看结果
              </el-button>
              <el-button
                v-if="task.status === 'failed'"
                size="small"
                type="warning"
                @click="handleRetry(task)"
              >
                <el-icon><RefreshRight /></el-icon>
                重试
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.task-center-view {
  max-width: 1200px;
  margin: 0 auto;
}

.guest-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  font-size: 13px;
  color: #1e40af;
}

.guest-banner .el-icon {
  font-size: 16px;
  color: #2563eb;
  flex-shrink: 0;
}

.task-center-header {
  margin-bottom: 20px;
}

.task-center-header h2 {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
  color: #1d2129;
}

.task-center-header p {
  margin: 0;
  font-size: 13px;
  color: #86909c;
}

.task-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.file-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.file-name {
  font-size: 14px;
  color: #1d2129;
}

.batch-tag {
  font-size: 11px;
}

:deep(.row-failed) {
  background-color: #fff5f5 !important;
}

:deep(.row-failed:hover > td) {
  background-color: #ffecec !important;
}

/* 手机端卡片列表 */
.mobile-card-list {
  display: none;
}

@media (max-width: 768px) {
  .desktop-table {
    display: none !important;
  }

  .mobile-card-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .task-card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  .task-card--failed {
    border-color: #fecaca;
    background: #fff5f5;
  }

  .task-card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }

  .task-card-name {
    font-size: 15px;
    font-weight: 500;
    color: #1d2129;
    line-height: 1.5;
    word-break: break-word;
    flex: 1;
  }

  .task-card-time {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 12px;
  }

  .task-card-actions {
    display: flex;
    gap: 8px;
  }

  .task-card-actions .el-button {
    flex: 1;
    height: 36px;
    font-size: 13px;
  }
}
</style>
