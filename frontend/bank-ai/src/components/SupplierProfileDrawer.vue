<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  OfficeBuilding,
  DocumentChecked,
  WarningFilled,
  InfoFilled,
  Clock,
  TrendCharts,
} from '@element-plus/icons-vue'
import api from '@/api'

interface RecentContract {
  task_id: string
  contract_name: string
  date: string
  risk_level: string
  creator_name?: string
}

interface SupplierProfileData {
  supplier_name: string
  total_contracts: number
  frequent_missing_clauses: string[]
  risk_summary: string
  recent_contracts: RecentContract[]
}

const visible = ref(false)
const loading = ref(false)
const profile = ref<SupplierProfileData | null>(null)
const currentSupplierName = ref('')

const open = async (supplierName: string) => {
  if (!supplierName || !supplierName.trim()) {
    ElMessage.warning('供应商名称不能为空')
    return
  }
  currentSupplierName.value = supplierName.trim()
  visible.value = true
  loading.value = true
  profile.value = null

  const requestUrl = `/api/v1/suppliers/profile/${encodeURIComponent(currentSupplierName.value)}`

  try {
    const res = await api.get(requestUrl)
    if (res.data.code === 200) {
      profile.value = res.data.data
    } else {
      ElMessage.error(res.data.message || '查询失败')
    }
  } catch (error: any) {
    const status = error.response?.status
    const msg =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      '查询供应商画像失败'
    if (status === 404) {
      ElMessage.info(`供应商「${currentSupplierName.value}」暂无画像数据`)
    } else {
      ElMessage.error(`[${status}] ${msg}`)
    }
    profile.value = null
  } finally {
    loading.value = false
  }
}

const getRiskTagType = (riskLevel: string) => {
  const level = riskLevel?.toLowerCase() || ''
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'success'
}

const getRiskLabel = (riskLevel: string) => {
  const level = riskLevel?.toLowerCase() || ''
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  return '低风险'
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

defineExpose({ open })
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="`${currentSupplierName} 画像档案`"
    size="80%"
    :destroy-on-close="false"
    append-to-body
    class="supplier-profile-drawer"
  >
    <div v-loading="loading" class="drawer-content">
      <el-empty v-if="!loading && !profile" description="该供应商暂无画像档案" />

      <template v-if="profile">
        <!-- 区块 A：核心指标 -->
        <div class="profile-section">
          <div class="section-header">
            <el-icon :size="18" color="#1e3a8a"><OfficeBuilding /></el-icon>
            <span class="section-title">核心指标</span>
          </div>
          <el-descriptions :column="1" border class="profile-descriptions">
            <el-descriptions-item label="供应商名称" label-class-name="desc-label">
              {{ profile.supplier_name }}
            </el-descriptions-item>
            <el-descriptions-item label="累计审查合同数" label-class-name="desc-label">
              <span class="highlight-number">{{ profile.total_contracts }}</span>
              <span class="highlight-unit">份</span>
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 区块 B：AI 画像洞察 -->
        <div v-if="profile.risk_summary" class="profile-section">
          <div class="section-header">
            <el-icon :size="18" color="#1e3a8a"><InfoFilled /></el-icon>
            <span class="section-title">AI 画像洞察</span>
          </div>
          <el-alert
            :description="profile.risk_summary"
            type="info"
            :closable="false"
            show-icon
            class="insight-alert"
          />
        </div>

        <!-- 区块 C：高频缺失条款 -->
        <div
          v-if="profile.frequent_missing_clauses && profile.frequent_missing_clauses.length > 0"
          class="profile-section"
        >
          <div class="section-header">
            <el-icon :size="18" color="#f53f3f"><WarningFilled /></el-icon>
            <span class="section-title">高频缺失条款</span>
          </div>
          <div class="tag-list">
            <el-tag
              v-for="(clause, index) in profile.frequent_missing_clauses"
              :key="index"
              :type="index % 2 === 0 ? 'danger' : 'warning'"
              effect="light"
              size="small"
              class="clause-tag"
              round
            >
              {{ clause }}
            </el-tag>
          </div>
        </div>

        <!-- 区块 D：历史溯源 -->
        <div class="profile-section">
          <div class="section-header">
            <el-icon :size="18" color="#1e3a8a"><TrendCharts /></el-icon>
            <span class="section-title">历史溯源</span>
          </div>
          <el-table
            v-if="profile.recent_contracts && profile.recent_contracts.length > 0"
            :data="profile.recent_contracts"
            style="width: 100%"
            size="small"
            :header-cell-style="{
              background: '#f7f8fa',
              color: '#4e5969',
              fontWeight: 600,
              fontSize: '13px',
            }"
            class="history-table"
          >
            <el-table-column prop="contract_name" label="合同名称" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="contract-name-cell">
                  <el-icon :size="14" color="#86909c"><DocumentChecked /></el-icon>
                  <span class="contract-name-text">{{ row.contract_name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="date" label="审查日期" width="145">
              <template #default="{ row }">
                <div class="date-cell">
                  <el-icon :size="12" color="#86909c"><Clock /></el-icon>
                  <span>{{ formatDate(row.date) }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="risk_level" label="风险等级" width="85">
              <template #default="{ row }">
                <el-tag :type="getRiskTagType(row.risk_level)" size="small" effect="light">
                  {{ getRiskLabel(row.risk_level) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无历史合同记录" :image-size="80" />
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.supplier-profile-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f2f5;
  font-weight: 600;
  font-size: 16px;
  color: #1d2129;
}

.drawer-content {
  padding: 4px 4px 20px;
}

.profile-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

/* 核心指标 */
.profile-descriptions :deep(.desc-label) {
  background: #f7f8fa;
  color: #4e5969;
  font-weight: 500;
  width: 130px;
}

.highlight-number {
  font-size: 22px;
  font-weight: 700;
  color: #1e3a8a;
  margin-right: 4px;
}

.highlight-unit {
  font-size: 13px;
  color: #86909c;
}

/* AI 洞察 Alert */
.insight-alert {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
}

.insight-alert :deep(.el-alert__description) {
  color: #0c4a6e;
  font-size: 13px;
  line-height: 1.7;
}

.insight-alert :deep(.el-alert__icon) {
  color: #0284c7;
}

/* 高频缺失条款 Tag */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.clause-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 0 12px;
  height: 26px;
}

/* 历史表格 */
.history-table :deep(.el-table__row) {
  transition: background 0.2s ease;
}

.history-table :deep(.el-table__row:hover > td) {
  background: #f7f8fa !important;
}

.contract-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.contract-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.date-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #4e5969;
}
</style>
