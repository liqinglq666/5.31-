<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  TrendCharts,
  Search,
  Download,
  View,
  EditPen,
  Document,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store'
import type { RecordItem } from '@/types/api'
import { riskLevelTag } from '@/utils/risk'
import { addRemark } from '@/api'

const userStore = useUserStore()

const props = defineProps<{
  records: RecordItem[]
  total: number
  page: number
  pageSize: number
  mode?: 'personal' | 'audit'
}>()

const emit = defineEmits<{
  (e: 'update:page', page: number): void
  (e: 'update:pageSize', pageSize: number): void
  (e: 'search', keyword: string, riskLevel: string): void
  (e: 'exportExcel', selection: RecordItem[]): void
  (e: 'exportPdf', selection: RecordItem[]): void
  (e: 'viewDetail', taskId: string): void
  (e: 'creatorChange', creatorId: string): void
  (e: 'archiveChange', isArchived: boolean): void
  (e: 'refresh'): void
}>()

const searchKeyword = ref('')
const searchRiskLevel = ref('')
const selectedRecords = ref<RecordItem[]>([])
const viewingId = ref<string | null>(null)
const creatorFilter = ref('all')
const archiveFilter = ref<'all' | 'archived' | 'unarchived'>('all')
const searchLoading = ref(false)
const exportLoading = ref(false)

// 备注弹窗
const remarkDialogVisible = ref(false)
const remarkTaskId = ref('')
const remarkContent = ref('')
const remarkLoading = ref(false)

// 当外部页码变化时同步（理论上不需要，因为受控）
const localPage = ref(props.page)
const localPageSize = ref(props.pageSize)

watch(
  () => props.page,
  (v) => {
    localPage.value = v
  }
)
watch(
  () => props.pageSize,
  (v) => {
    localPageSize.value = v
  }
)

const isAudit = computed(() => props.mode === 'audit')

const cardTitle = computed(() =>
  isAudit.value ? '公司审计档案' : '我的比对记录'
)

// 从当前记录中提取唯一的处理人列表（仅 audit 模式使用）
const creatorOptions = computed(() => {
  const map = new Map<string, string>()
  props.records.forEach((r) => {
    if (r.creator_id) {
      const label = `${r.creator_name || '未知'}${r.creator_emp_id ? ` (${r.creator_emp_id})` : ''}`
      map.set(r.creator_id, label)
    }
  })
  return Array.from(map.entries()).map(([id, label]) => ({ id, label }))
})

const onSearch = async () => {
  searchLoading.value = true
  try {
    await emit('search', searchKeyword.value, searchRiskLevel.value)
  } finally {
    searchLoading.value = false
  }
}

const onCreatorTabChange = (val: string) => {
  creatorFilter.value = val
  emit('creatorChange', val === 'all' ? '' : val)
}

const onArchiveTabChange = (val: string) => {
  archiveFilter.value = val as 'all' | 'archived' | 'unarchived'
  if (val === 'archived') {
    emit('archiveChange', true)
  } else if (val === 'unarchived') {
    emit('archiveChange', false)
  } else {
    emit('archiveChange', undefined as any)
  }
}

const onPageChange = (page: number) => {
  localPage.value = page
  emit('update:page', page)
}

const onPageSizeChange = (pageSize: number) => {
  localPageSize.value = pageSize
  emit('update:pageSize', pageSize)
}

const onSelectionChange = (selection: RecordItem[]) => {
  selectedRecords.value = selection
}

const handleExport = async () => {
  if (selectedRecords.value.length === 0) {
    ElMessage.warning('请先在表格中勾选需要导出的记录')
    return
  }
  exportLoading.value = true
  try {
    await emit('exportExcel', selectedRecords.value)
  } finally {
    exportLoading.value = false
  }
}

const handleExportPdf = () => {
  if (selectedRecords.value.length === 0) {
    ElMessage.warning('请先在表格中勾选需要导出的记录')
    return
  }
  emit('exportPdf', selectedRecords.value)
}

const handleViewDetail = async (row: RecordItem) => {
  viewingId.value = row.task_id
  try {
    emit('viewDetail', row.task_id)
  } finally {
    viewingId.value = null
  }
}

const openRemarkDialog = (row: RecordItem) => {
  remarkTaskId.value = row.task_id
  remarkContent.value = row.remark || ''
  remarkDialogVisible.value = true
}

const handleSaveRemark = async () => {
  if (!remarkContent.value.trim()) {
    ElMessage.warning('请输入备注内容')
    return
  }
  remarkLoading.value = true
  try {
    await addRemark(remarkTaskId.value, remarkContent.value.trim())
    ElMessage.success('备注已保存')
    remarkDialogVisible.value = false
    emit('refresh')
  } catch (_err: any) {
    ElMessage.error(_err.response?.data?.detail || '备注保存失败')
  } finally {
    remarkLoading.value = false
  }
}
</script>

<template>
  <section class="record-list-section">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ cardTitle }}</span>
        </div>
      </template>

      <!-- 审计模式：处理人快捷筛选 Tab -->
      <div v-if="isAudit" class="creator-filter">
        <el-tabs v-model="creatorFilter" type="card" @tab-change="onCreatorTabChange">
          <el-tab-pane label="全部" name="all" />
          <el-tab-pane
            v-for="opt in creatorOptions"
            :key="opt.id"
            :label="opt.label"
            :name="opt.id"
          />
        </el-tabs>
      </div>

      <!-- 审计模式：归档状态快捷筛选 Tab -->
      <div v-if="isAudit" class="archive-filter">
        <el-tabs v-model="archiveFilter" type="card" @tab-change="onArchiveTabChange">
          <el-tab-pane label="全部记录" name="all" />
          <el-tab-pane label="已归档" name="archived" />
          <el-tab-pane label="未归档" name="unarchived" />
        </el-tabs>
      </div>

      <div class="history-toolbar">
        <el-input
          v-model="searchKeyword"
          placeholder="请输入项目名称关键字"
          clearable
          style="width: 220px"
          @keyup.enter="onSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-select
          v-model="searchRiskLevel"
          placeholder="风险等级"
          clearable
          style="width: 140px"
        >
          <el-option label="全部" value="" />
          <el-option label="高风险" value="high" />
          <el-option label="低风险" value="low" />
          <el-option label="安全" value="safe" />
        </el-select>

        <el-button type="primary" :loading="searchLoading" @click="onSearch">查询</el-button>

        <el-button type="success" :loading="exportLoading" class="mobile-hide-btn" @click="handleExport">
          <el-icon><Download /></el-icon>
          批量导出 Excel
        </el-button>
        <el-button type="danger" class="mobile-hide-btn" @click="handleExportPdf">
          <el-icon><Document /></el-icon>
          批量导出 PDF
        </el-button>
      </div>

      <el-table
        :data="records"
        border
        style="width: 100%"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="55" align="center" />
        <el-table-column
          prop="project_name"
          label="项目名称"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column prop="created_at" label="创建时间" width="170" class-name="mobile-hide-col" />
        <el-table-column prop="status" label="状态" width="90" class-name="mobile-hide-col">
          <template #default="{ row }">
            <el-tag
              v-if="row.status === 'completed'"
              type="success"
              size="small"
              >已完成</el-tag
            >
            <el-tag
              v-else-if="row.status === 'failed'"
              type="danger"
              size="small"
              >失败</el-tag
            >
            <el-tag v-else type="info" size="small">处理中</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="risk_level" label="风险等级" width="100">
          <template #default="{ row }">
            <el-tag
              :type="riskLevelTag(row.risk_level).type"
              effect="plain"
              size="small"
            >
              {{ riskLevelTag(row.risk_level).text }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 审计模式下固定显示处理人列 -->
        <el-table-column
          v-if="isAudit"
          prop="creator_name"
          label="处理人"
          width="140"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <span>
              {{ row.creator_name || row.creator_emp_id || '-' }}
              <span v-if="row.creator_emp_id" class="emp-id">({{ row.creator_emp_id }})</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column
          v-else
          prop="creator_name"
          label="检测人员"
          width="120"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <span>{{ row.creator_name || row.creator_emp_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="conclusion"
          label="比对结论"
          min-width="200"
          show-overflow-tooltip
          class-name="mobile-hide-col"
        />
        <!-- 归档状态列 -->
        <el-table-column
          v-if="isAudit"
          label="归档状态"
          width="90"
          align="center"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <el-tag
              v-if="row.is_archived"
              type="success"
              size="small"
              effect="dark"
            >已归档</el-tag>
            <el-tag v-else type="info" size="small">未归档</el-tag>
          </template>
        </el-table-column>
        <!-- 备注列（所有人可见） -->
        <el-table-column
          label="备注"
          min-width="160"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <div v-if="row.remark" class="remark-cell">
              <el-tooltip :content="row.remark" placement="top" :show-after="300">
                <span class="remark-text">{{ row.remark }}</span>
              </el-tooltip>
              <div class="remark-meta">
                {{ row.remark_reviewer_name || row.remark_reviewer_emp_id || '-' }}
                <span v-if="row.remark_time">
                  · {{ row.remark_time }}
                </span>
              </div>
            </div>
            <span v-else class="remark-empty">-</span>
          </template>
        </el-table-column>
        <!-- 已归档筛选模式下显示归档时间与归档人 -->
        <el-table-column
          v-if="isAudit && archiveFilter === 'archived'"
          label="归档时间"
          width="170"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <span v-if="row.archive_time">
              {{ row.archive_time }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="isAudit && archiveFilter === 'archived'"
          label="归档人"
          width="140"
          class-name="mobile-hide-col"
        >
          <template #default="{ row }">
            <span>
              {{ row.reviewer_name || row.reviewer_emp_id || '-' }}
              <span v-if="row.reviewer_emp_id" class="emp-id">({{ row.reviewer_emp_id }})</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-btns">
              <el-button
                type="primary"
                size="small"
                :loading="viewingId === row.task_id"
                @click="handleViewDetail(row)"
              >
                <el-icon><View /></el-icon>
              </el-button>
              <el-button
                type="warning"
                size="small"
                class="mobile-hide-btn"
                @click="openRemarkDialog(row)"
              >
                <el-icon><EditPen /></el-icon>
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="history-pagination">
        <el-pagination
          v-model:current-page="localPage"
          v-model:page-size="localPageSize"
          :total="total"
          layout="total, sizes, prev, pager, next"
          :page-sizes="[10, 20, 50]"
          @current-change="onPageChange"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>

    <!-- 备注弹窗 -->
    <el-dialog
      v-model="remarkDialogVisible"
      title="添加/编辑备注"
      width="90%"
      :style="{ maxWidth: '500px' }"
      align-center
    >
      <el-input
        v-model="remarkContent"
        type="textarea"
        :rows="4"
        placeholder="请输入备注信息..."
        maxlength="500"
        show-word-limit
      />
      <template #footer>
        <el-button @click="remarkDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="remarkLoading" @click="handleSaveRemark">
          保存备注
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.record-list-section {
  max-width: 1400px;
  margin: 24px auto 0;
  padding: 0 24px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}

.history-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.history-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.creator-filter {
  margin-bottom: 16px;
}

.creator-filter :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.archive-filter {
  margin-bottom: 16px;
}

.archive-filter :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.emp-id {
  color: #64748b;
  font-size: 12px;
  margin-left: 4px;
}

.action-btns {
  display: flex;
  justify-content: center;
  gap: 6px;
}

.remark-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.remark-text {
  font-size: 13px;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.remark-meta {
  font-size: 11px;
  color: #94a3b8;
}

.remark-empty {
  color: #94a3b8;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 768px) {
  .record-list-section {
    max-width: 100vw;
    margin: 12px auto 0;
    padding: 0 12px;
  }

  .history-toolbar {
    gap: 8px;
    margin-bottom: 12px;
  }

  .history-toolbar .el-input {
    width: 140px !important;
  }

  .history-toolbar .el-select {
    width: 100px !important;
  }

  /* 手机端隐藏元素 */
  .mobile-hide-btn {
    display: none !important;
  }

  :deep(.mobile-hide-col) {
    display: none !important;
  }

  /* 表格容器横向滚动 */
  :deep(.el-table) {
    width: 100%;
  }

  :deep(.el-table__body-wrapper) {
    overflow-x: auto;
  }

  :deep(.el-table__header-wrapper th) {
    padding: 6px 4px;
    font-size: 11px;
  }

  :deep(.el-table__body-wrapper td) {
    padding: 6px 4px;
  }

  .remark-text {
    max-width: 100px;
  }

  .action-btns {
    flex-direction: row;
    gap: 6px;
  }

  .history-pagination {
    justify-content: center;
  }

  .history-pagination :deep(.el-pagination__sizes) {
    display: none;
  }
}
</style>
