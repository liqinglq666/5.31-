<script setup lang="ts">
import { computed } from 'vue'
import { UserFilled } from '@element-plus/icons-vue'
import type { TaskResult } from '@/types/api'
import { riskLevelTag } from '@/utils/risk'

const props = defineProps<{
  taskResult: TaskResult | null
  creatorName?: string
  creatorEmpId?: string
  processMode?: string
  isArchived: boolean
  archiveTime?: string
  reviewerInfo?: {
    name?: string
    employee_id?: string
    position?: string
  }
  createdAt?: string
}>()

const riskMeta = computed(() => {
  const level = props.taskResult?.comparison?.risk_level || ''
  return riskLevelTag(level)
})

const totalRiskCount = computed(() => {
  const diffCount = props.taskResult?.comparison?.differences?.length || 0
  const missingCount = props.taskResult?.comparison?.missing_items?.length || 0
  return diffCount + missingCount
})

const complianceScore = computed(() => {
  const diffs = props.taskResult?.comparison?.differences
  if (!diffs?.length) {
    const missing = props.taskResult?.comparison?.missing_items?.length || 0
    if (missing === 0) return 100
  }
  // 兼容旧格式：differences 为字符串数组且只有一条“一致未发现”
  if (diffs?.length === 1 && typeof diffs[0] === 'string') {
    const first = diffs[0] as string
    if (first.includes('一致') && first.includes('未发现')) return 100
  }
  const level = props.taskResult?.comparison.risk_level || 'low'
  const deduction = level === 'high' ? 25 : level === 'medium' ? 15 : 10
  return Math.max(0, 100 - totalRiskCount.value * deduction)
})

const scoreColor = computed(() => {
  const s = complianceScore.value
  if (s >= 80) return '#16a34a'
  if (s >= 60) return '#f59e0b'
  return 'var(--el-color-danger)'
})

const scoreLabel = computed(() => {
  const s = complianceScore.value
  if (s >= 80) return '优良'
  if (s >= 60) return '一般'
  return '高危'
})

const auditInfo = computed(() => ({
  creator: props.creatorName || props.creatorEmpId || '—',
  empId: props.creatorEmpId || '—',
  time: props.createdAt || '—',
  mode:
    props.processMode === 'RAG'
      ? 'RAG 深度检索引擎'
      : '标准全量比对引擎',
  archive: props.isArchived ? '已归档' : '未归档',
}))

const aiConclusion = computed((): string => {
  const comp = props.taskResult?.comparison
  if (!comp) return '暂无结论'

  const level = (comp.risk_level || 'low').toLowerCase()
  const diffCount = (comp.differences?.length || 0)
  const missingCount = (comp.missing_items?.length || 0)
  const bid = props.taskResult?.bid_info
  const contract = props.taskResult?.contract_info

  const vendorMismatch = bid?.vendor_name && contract?.vendor_name && bid.vendor_name !== contract.vendor_name
  const amountMismatch = Number(bid?.total_amount || 0) > 0 && Number(contract?.total_amount || 0) > 0 && Number(bid?.total_amount) !== Number(contract?.total_amount)
  const penaltyFields = ['delay_daily_rate', 'penalty_cap_rate', 'termination_penalty_rate']
  const penaltyMismatch = penaltyFields.some((f) => {
    const b = Number(bid?.[f as keyof typeof bid] || 0)
    const c = Number(contract?.[f as keyof typeof contract] || 0)
    return b > 0 && c >= 0 && Math.abs(b - c) > 0.0001
  })

  if (level === 'high' || missingCount > 0) {
    const parts: string[] = []
    if (missingCount > 0) parts.push(`缺失 ${missingCount} 项关键条款`)
    if (vendorMismatch) parts.push('供应商主体变更')
    if (amountMismatch) parts.push('合同金额偏离中标结果')
    if (penaltyMismatch) parts.push('违约金比例下调')
    if (diffCount > 0 && parts.length === 0) parts.push(`存在 ${diffCount} 项重大差异`)
    const reason = parts.length ? parts.join('、') : '存在重大合规风险'
    return `本次比对发现${reason}，建议暂缓签署并启动整改流程。`
  }

  if (level === 'medium' || diffCount > 0) {
    const parts: string[] = []
    if (diffCount > 0) parts.push(`${diffCount} 项条款差异`)
    if (amountMismatch) parts.push('金额不一致')
    if (penaltyMismatch) parts.push('违约条款弱化')
    const reason = parts.length ? parts.join('、') : '若干条款需关注'
    return `本次比对发现${reason}，建议由法务复核后签署。`
  }

  return '本次比对未发现重大风险，合同条款与采购结果基本保持一致，可按正常流程签署。'
})

function formatArchiveTime(dt: string) {
  // 后端已返回格式化后的北京时间字符串，直接显示
  return dt
}
</script>

<template>
  <div class="compliance-score">
    <!-- 检测人员信息条 -->
    <div v-if="creatorName || creatorEmpId" class="creator-banner">
      <el-icon><UserFilled /></el-icon>
      <span class="creator-text">
        检测人员：{{ creatorName || creatorEmpId }}
        <span v-if="creatorName && creatorEmpId">
          （工号: {{ creatorEmpId }}）
        </span>
      </span>
    </div>

    <!-- 引擎来源 -->
    <div v-if="processMode" class="engine-banner">
      <el-tag
        :type="processMode === 'RAG' ? 'primary' : 'success'"
        effect="light"
        size="small"
      >
        本次审查由 {{ processMode === 'RAG' ? 'RAG 深度检索引擎' : '标准全量比对引擎' }} 完成
      </el-tag>
    </div>

    <!-- 顶部版头：合规评分 + 审计留痕 -->
    <div class="report-dashboard">
      <el-row :gutter="16" align="middle" class="report-header-row">
        <el-col :xs="24" :md="8">
          <div id="section-score" class="dashboard-card score-card">
            <div class="dashboard-title">合规评分卡</div>
            <div class="score-body">
              <el-progress
                type="dashboard"
                :percentage="complianceScore"
                :color="scoreColor"
                :stroke-width="10"
                :width="130"
              />
              <div class="score-label" :style="{ color: scoreColor }">
                {{ scoreLabel }}
              </div>
              <div class="score-hint">基于风险点数量动态计算，满分 100</div>
            </div>
          </div>
        </el-col>

        <el-col :xs="24" :md="1" class="divider-col">
          <el-divider direction="vertical" class="header-divider" />
        </el-col>

        <el-col :xs="24" :md="15">
          <div id="section-audit" class="dashboard-card audit-card">
            <div class="dashboard-title">审计留痕区</div>
            <div class="audit-body">
              <div class="audit-row">
                <span class="audit-label">检测人员</span>
                <span class="audit-value">{{ auditInfo.creator }}</span>
              </div>
              <div class="audit-row">
                <span class="audit-label">工　　号</span>
                <span class="audit-value">{{ auditInfo.empId }}</span>
              </div>
              <div class="audit-row">
                <span class="audit-label">检测时间</span>
                <span class="audit-value">{{ auditInfo.time }}</span>
              </div>
              <div class="audit-row">
                <span class="audit-label">算法模式</span>
                <span class="audit-value">{{ auditInfo.mode }}</span>
              </div>
              <div class="audit-row">
                <span class="audit-label">归档状态</span>
                <el-tag :type="isArchived ? 'success' : 'info'" size="small">
                  {{ auditInfo.archive }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 数字化存证章 -->
    <div v-if="isArchived" class="report-section archive-section">
      <div class="digital-seal">
        <div class="seal-title">数字化存证章</div>
        <div class="seal-body">
          <div class="seal-row">
            <span class="seal-label">AI 审查结论：</span>
            <span class="seal-value">
              {{ aiConclusion }}
            </span>
          </div>
          <div v-if="reviewerInfo?.name" class="seal-row">
            <span class="seal-label">审核人员：</span>
            <span class="seal-value">{{ reviewerInfo.name }}</span>
          </div>
          <div v-if="reviewerInfo?.employee_id" class="seal-row">
            <span class="seal-label">工　　号：</span>
            <span class="seal-value">{{ reviewerInfo.employee_id }}</span>
          </div>
          <div v-if="reviewerInfo?.position" class="seal-row">
            <span class="seal-label">职　　务：</span>
            <span class="seal-value">{{ reviewerInfo.position }}</span>
          </div>
          <div v-if="archiveTime" class="seal-row">
            <span class="seal-label">归档时间：</span>
            <span class="seal-value">{{ formatArchiveTime(archiveTime) }}</span>
          </div>
        </div>
        <div class="seal-stamp">已归档</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.compliance-score {
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
}

.creator-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(90deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 10px 16px;
  margin-bottom: 14px;
  color: #1e40af;
  font-size: 14px;
  font-weight: 600;
}

.creator-text {
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
}

.engine-banner {
  text-align: center;
  margin-bottom: 18px;
}

.report-dashboard {
  margin-bottom: 24px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.report-header-row {
  min-height: 200px;
}

.divider-col {
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-divider {
  height: 140px;
  margin: 0;
  border-left-color: #e2e8f0;
}

.dashboard-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 16px;
  height: 100%;
}

.dashboard-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  border-left: 4px solid #2563eb;
  padding-left: 10px;
  margin-bottom: 12px;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.score-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.score-label {
  font-size: 18px;
  font-weight: 700;
}

.score-hint {
  font-size: 12px;
  color: #94a3b8;
}

.audit-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.audit-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: #334155;
  padding: 6px 10px;
  background: #fff;
  border-radius: 6px;
}

.audit-label {
  color: #64748b;
  font-weight: 500;
}

.audit-value {
  color: #1e293b;
  font-weight: 600;
}

.report-section {
  margin-bottom: 22px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e40af;
  border-left: 4px solid #2563eb;
  padding-left: 10px;
  margin-bottom: 12px;
}

.conclusion-box {
  padding: 14px 16px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.conclusion-risk {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
}

.risk-label {
  font-weight: 700;
}

.conclusion-text {
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}

.risk-high {
  background: #fef2f2;
  border-color: #fecaca;
}
.risk-high .conclusion-risk,
.risk-high .risk-label {
  color: #dc2626;
}

.risk-medium {
  background: #fffbeb;
  border-color: #fde68a;
}
.risk-medium .conclusion-risk,
.risk-medium .risk-label {
  color: #d97706;
}

.risk-low {
  background: #f0fdf4;
  border-color: #bbf7d0;
}
.risk-low .conclusion-risk,
.risk-low .risk-label {
  color: #16a34a;
}

.archive-section {
  page-break-inside: avoid;
  break-inside: avoid;
}

.digital-seal {
  position: relative;
  border: 2px solid #991b1b;
  border-radius: 8px;
  background: #fafafa;
  padding: 20px 24px;
  margin-top: 8px;
}

.seal-title {
  font-size: 18px;
  font-weight: 700;
  color: #991b1b;
  text-align: center;
  letter-spacing: 4px;
  margin-bottom: 16px;
  border-bottom: 1px dashed #991b1b;
  padding-bottom: 10px;
}

.seal-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.seal-row {
  font-size: 14px;
  color: #334155;
}

.seal-label {
  font-weight: 600;
  color: #475569;
}

.seal-value {
  color: #1e293b;
}

.seal-stamp {
  position: absolute;
  top: 50%;
  right: 24px;
  transform: translateY(-50%) rotate(-12deg);
  width: 84px;
  height: 84px;
  border: 3px solid #dc2626;
  border-radius: 50%;
  color: #dc2626;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.35;
  pointer-events: none;
}
</style>
