<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getStats, getRecords, exportExcel } from '@/api'
import { useUserStore } from '@/store'
import type { StatsData, RecordItem } from '@/types/api'
import { useCompareStore } from '@/store/compare'
import { useBatchPdfExport } from '@/composables/useBatchPdfExport'
import MainLayout from '@/layouts/MainLayout.vue'
import Dashboard from '@/components/Dashboard.vue'
import CompareDetail from '@/components/CompareDetail.vue'
import RecordList from '@/components/RecordList.vue'
import StatsBar from '@/components/StatsBar.vue'
import FileUploadPanel from '@/components/FileUploadPanel.vue'
import TaskCenterView from '@/components/TaskCenterView.vue'
import BatchPdfExportModal from '@/components/BatchPdfExportModal.vue'
import PdfViewer from '@/components/PdfViewer/index.vue'
import ModelManagement from '@/views/Admin/ModelManagement.vue'
import type { VisualEvidence } from '@/types/api'

const compareStore = useCompareStore()
const userStore = useUserStore()
const { visible: pdfExportVisible, items: pdfExportItems, currentIndex: pdfExportCurrentIndex, isRunning: pdfExportIsRunning, startExport: startPdfExport, cancel: cancelPdfExport } = useBatchPdfExport()

// ---------------------------------------------------------------------------
// V3.1 视觉溯源：PDF 弹窗定位
// ---------------------------------------------------------------------------
const pdfDialogVisible = ref(false)
const currentPdfHighlight = ref<VisualEvidence | null>(null)
const currentBlobUrl = ref('')

type MenuKey = 'dashboard' | 'compare' | 'tasks' | 'review' | 'personal' | 'audit' | 'admin'
const activeMenu = ref<MenuKey>('dashboard')
const isCompareFullscreen = ref(false)

const fileUploadPanelRef = ref<InstanceType<typeof FileUploadPanel> | null>(null)
const detailTransitionTrigger = ref(0)

// ---------------------------------------------------------------------------
// 移动端响应式
// ---------------------------------------------------------------------------
const isMobile = ref(false)
const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// ---------------------------------------------------------------------------
// 比对流程
// ---------------------------------------------------------------------------
const handleStartCompare = async (formData: FormData) => {
  try {
    const taskId = await compareStore.startTask(formData)
    ElMessage.success(`比对任务已提交，Task ID: ${taskId}`)
    fetchStats()
    fetchPersonalRecords()
  } catch (err: any) {
    ElMessage.error(err.message || '任务提交失败')
  }
}

const handleStartBatch = async (formDataList: FormData[], concurrency: number) => {
  if (formDataList.length === 0) return
  const taskIds = await compareStore.runBatchCompare(formDataList, (current, total) => {
    fileUploadPanelRef.value?.updateBatchProgress(current, total)
  }, concurrency)
  ElMessage.success(`已提交 ${taskIds.length} 个后台比对任务`)
  fetchStats()
  fetchPersonalRecords()
}

onUnmounted(() => {
  compareStore.clearCompareInterval()
})

// ---------------------------------------------------------------------------
// 视觉溯源：定位原文（V3.1）
// ---------------------------------------------------------------------------
const handleLocateEvidence = (evidence: VisualEvidence) => {
  const taskId = compareStore.currentTaskId
  const blobUrl = taskId ? compareStore.getContractBlobUrl(taskId) : undefined
  if (!blobUrl) {
    ElMessage.warning('当前为历史任务或文件已过期，无法定位原文，请重新上传比对')
    return
  }
  currentBlobUrl.value = blobUrl
  currentPdfHighlight.value = evidence
  pdfDialogVisible.value = true
}

// ---------------------------------------------------------------------------
// 数据看板
// ---------------------------------------------------------------------------
const stats = ref<StatsData>({
  total_reviews: 0,
  today_new: 0,
  high_risk_ratio: 0,
  avg_duration_seconds: 0,
})

const fetchStats = async () => {
  try {
    const res = await getStats()
    stats.value = res.data.data
  } catch (_err) {
    // 静默失败
  }
}

// ---------------------------------------------------------------------------
// 我的比对记录
// ---------------------------------------------------------------------------
const personalRecords = ref<RecordItem[]>([])
const personalTotal = ref(0)
const personalPage = ref(1)
const personalPageSize = ref(10)
const personalKeyword = ref('')
const personalRiskLevel = ref('')

const fetchPersonalRecords = async () => {
  try {
    const res = await getRecords({
      page: personalPage.value,
      page_size: personalPageSize.value,
      keyword: personalKeyword.value,
      risk_level: personalRiskLevel.value,
    })
    personalTotal.value = res.data.data.total
    personalRecords.value = res.data.data.list
  } catch (_err) {
    ElMessage.error('获取历史记录失败')
  }
}

const onPersonalSearch = () => {
  personalPage.value = 1
  fetchPersonalRecords()
}

// ---------------------------------------------------------------------------
// 公司审计档案
// ---------------------------------------------------------------------------
const auditRecords = ref<RecordItem[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPageSize = ref(10)
const auditKeyword = ref('')
const auditRiskLevel = ref('')
const auditCreatorId = ref('')
const auditIsArchived = ref<boolean | undefined>(undefined)

const fetchAuditRecords = async () => {
  try {
    const params: any = {
      page: auditPage.value,
      page_size: auditPageSize.value,
      keyword: auditKeyword.value,
      risk_level: auditRiskLevel.value,
      scope: 'all',
      creator_id: auditCreatorId.value,
    }
    if (auditIsArchived.value !== undefined) {
      params.is_archived = auditIsArchived.value
    }
    const res = await getRecords(params)
    auditTotal.value = res.data.data.total
    auditRecords.value = res.data.data.list
  } catch (_err) {
    ElMessage.error('获取审计档案失败')
  }
}

const onAuditSearch = () => {
  auditPage.value = 1
  fetchAuditRecords()
}

const onAuditCreatorChange = (creatorId: string) => {
  auditCreatorId.value = creatorId
  auditPage.value = 1
  fetchAuditRecords()
}

const onAuditArchiveChange = (isArchived: boolean | undefined) => {
  auditIsArchived.value = isArchived
  auditPage.value = 1
  fetchAuditRecords()
}

// ---------------------------------------------------------------------------
// 公共操作
// ---------------------------------------------------------------------------
const handleExportExcel = async (selection: RecordItem[]) => {
  if (selection.length === 0) {
    ElMessage.warning('请先在表格中勾选需要导出的记录')
    return
  }
  const taskIds = selection.map((r) => r.task_id).join(',')
  try {
    const res = await exportExcel(taskIds)
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'compare_records.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (_err) {
    ElMessage.error('导出失败')
  }
}

const handleExportPdf = async (selection: RecordItem[]) => {
  if (selection.length === 0) {
    ElMessage.warning('请先在表格中勾选需要导出的记录')
    return
  }
  await startPdfExport(selection)
}

const handleViewDetail = async (taskId: string) => {
  const ok = await compareStore.loadTaskResult(taskId)
  if (ok) {
    activeMenu.value = 'compare'
    detailTransitionTrigger.value++
    ElMessage.success('已加载比对详情')
  } else {
    ElMessage.warning('该记录暂无比对结果')
  }
}

// ---------------------------------------------------------------------------
// 菜单切换
// ---------------------------------------------------------------------------
// 游客禁止访问的菜单（compare 允许查看结果但不允许上传）
const GUEST_FORBIDDEN_MENUS = new Set(['audit', 'admin'])

const onMenuSelect = (index: string) => {
  if (userStore.isGuest && GUEST_FORBIDDEN_MENUS.has(index)) {
    ElMessage.warning('游客模式暂不支持此功能，请注册登录后使用')
    activeMenu.value = 'dashboard'
    return
  }
  if (index === 'personal') {
    fetchPersonalRecords()
  } else if (index === 'audit') {
    fetchAuditRecords()
  } else if (index === 'dashboard') {
    fetchStats()
  }
}

// 拦截游客切换到禁止菜单
watch(activeMenu, (val) => {
  if (userStore.isGuest && GUEST_FORBIDDEN_MENUS.has(val)) {
    activeMenu.value = 'dashboard'
    ElMessage.warning('游客模式暂不支持此功能')
  }
})

// ---------------------------------------------------------------------------
// 页面刷新后恢复进行中的任务
// ---------------------------------------------------------------------------
const restoreTasks = async () => {
  await compareStore.restoreRunningTasks()
}

// ---------------------------------------------------------------------------
// Dashboard 卡片点击
// ---------------------------------------------------------------------------
const handleGoToList = (filter: 'all' | 'risk' | 'today') => {
  activeMenu.value = 'personal'
  if (filter === 'risk') {
    personalRiskLevel.value = 'high'
  } else {
    personalRiskLevel.value = ''
  }
  fetchPersonalRecords()
}

onMounted(() => {
  fetchStats()
  fetchPersonalRecords()
  restoreTasks()
})
</script>

<template>
  <MainLayout v-model:active-menu="activeMenu" @menu-select="onMenuSelect">
    <!-- 数据驾驶舱 -->
    <div v-show="activeMenu === 'dashboard'" class="dashboard-view">
      <Dashboard
        @new-task="userStore.isGuest ? ElMessage.warning('游客模式暂不支持上传比对') : (activeMenu = 'compare')"
        @go-to-list="handleGoToList"
      />
    </div>

    <!-- 智能比对 -->
    <div v-show="activeMenu === 'compare'" class="compare-view">
      <StatsBar v-show="!(isMobile && compareStore.hasReport)" :stats="stats" />
      <main class="main-content">
        <el-row :gutter="24" class="compare-row">
          <el-col
            v-show="!isCompareFullscreen"
            :xs="24"
            :lg="compareStore.hasReport ? 7 : 16"
            :offset-lg="compareStore.hasReport ? 0 : 4"
            class="upload-col"
            :class="{ 'upload-col--compact': compareStore.hasReport }"
          >
            <div v-if="userStore.isGuest" class="guest-block" :class="{ 'guest-block--has-report': compareStore.hasReport }">
              <el-empty description="游客模式不支持上传比对功能" />
            </div>
            <FileUploadPanel
              v-else
              ref="fileUploadPanelRef"
              :compact="compareStore.hasReport"
              v-model:loading="compareStore.isComparing"
              @start="handleStartCompare"
              @start-batch="handleStartBatch"
            />
          </el-col>

          <el-col
            :xs="24"
            :lg="isCompareFullscreen ? 24 : (compareStore.hasReport ? 17 : 8)"
            class="detail-col"
            :class="{ 'detail-col--expanded': compareStore.hasReport, 'detail-col--fullscreen': isCompareFullscreen }"
          >
            <div :key="detailTransitionTrigger" class="compare-panel-enter">
              <CompareDetail
                :task-result="compareStore.taskResult"
                :task-id="compareStore.currentTaskId"
                :creator-name="compareStore.currentCreatorName"
                :creator-emp-id="compareStore.currentCreatorEmpId"
                :is-fullscreen="isCompareFullscreen"
                @locate="handleLocateEvidence"
                @toggle-fullscreen="isCompareFullscreen = !isCompareFullscreen"
              />
            </div>
          </el-col>
        </el-row>
      </main>
    </div>

    <!-- 任务中心 -->
    <div v-show="activeMenu === 'tasks'" class="tasks-view">
      <TaskCenterView @view-result="activeMenu = 'compare'" />
    </div>

    <!-- 我的比对记录 -->
    <div v-show="activeMenu === 'personal'" class="records-view">
      <RecordList
        v-model:page="personalPage"
        v-model:page-size="personalPageSize"
        mode="personal"
        :records="personalRecords"
        :total="personalTotal"
        @search="
          (k, r) => {
            personalKeyword = k
            personalRiskLevel = r
            onPersonalSearch()
          }
        "
        @export-excel="handleExportExcel"
        @export-pdf="handleExportPdf"
        @view-detail="handleViewDetail"
        @refresh="fetchPersonalRecords"
        @update:page="fetchPersonalRecords"
        @update:page-size="fetchPersonalRecords"
      />
    </div>

    <!-- 公司审计档案 -->
    <div v-show="activeMenu === 'audit'" class="audit-view">
      <RecordList
        v-model:page="auditPage"
        v-model:page-size="auditPageSize"
        mode="audit"
        :records="auditRecords"
        :total="auditTotal"
        @search="
          (k, r) => {
            auditKeyword = k
            auditRiskLevel = r
            onAuditSearch()
          }
        "
        @creator-change="onAuditCreatorChange"
        @archive-change="onAuditArchiveChange"
        @export-excel="handleExportExcel"
        @export-pdf="handleExportPdf"
        @view-detail="handleViewDetail"
        @refresh="fetchAuditRecords"
        @update:page="fetchAuditRecords"
        @update:page-size="fetchAuditRecords"
      />
    </div>
    <!-- 系统管理 -->
    <div v-if="activeMenu === 'admin'" class="admin-view">
      <ModelManagement />
    </div>

    <!-- 批量导出 PDF 进度弹窗 -->
    <BatchPdfExportModal
      v-model:visible="pdfExportVisible"
      :items="pdfExportItems"
      :current-index="pdfExportCurrentIndex"
      :is-running="pdfExportIsRunning"
      @cancel="cancelPdfExport"
    />

    <!-- V3.1 视觉溯源：PDF 原文定位弹窗 -->
    <el-dialog
      v-model="pdfDialogVisible"
      title="合同原文定位"
      width="75%"
      :style="{ maxWidth: '1200px' }"
      :close-on-click-modal="false"
      destroy-on-close
      class="pdf-locator-dialog"
    >
      <PdfViewer
        v-if="currentBlobUrl"
        :url="currentBlobUrl"
        :highlight="currentPdfHighlight || undefined"
      />
    </el-dialog>
  </MainLayout>
</template>

<style scoped>
.main-content {
  max-width: 1400px;
  margin: 0 auto;
}

.compare-panel-enter {
  animation: slideIn 0.5s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.compare-row {
  align-items: flex-start;
}

.upload-col,
.detail-col {
  transition: all 0.45s cubic-bezier(0.4, 0, 0.2, 1);
}

.upload-col--compact {
  opacity: 1;
}

.detail-col--expanded {
  opacity: 1;
}

.pdf-locator-dialog :deep(.el-dialog__body) {
  padding: 0;
  height: 70vh;
}

.guest-block {
  padding: 40px 20px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  text-align: center;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 768px) {
  .main-content {
    max-width: 100vw;
    margin: 0;
    padding: 0;
  }

  .compare-row {
    margin: 0 !important;
  }

  .upload-col,
  .detail-col {
    padding-left: 0 !important;
    padding-right: 0 !important;
  }

  .pdf-locator-dialog :deep(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
    margin-top: 2vh !important;
  }

  .pdf-locator-dialog :deep(.el-dialog__body) {
    height: 70vh;
    padding: 8px;
  }

  /* 手机端有比对结果时隐藏 empty 区域 */
  .guest-block--has-report {
    display: none !important;
  }
}
</style>
