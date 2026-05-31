<script setup lang="ts">
import { computed } from 'vue'
import type { TaskResult, DifferenceItem, MissingItem } from '@/types/api'

const props = defineProps<{
  taskResult: TaskResult
  creatorName?: string
  creatorEmpId?: string
}>()

const riskLevel = computed(() => props.taskResult.comparison?.risk_level || 'safe')
const confidenceScore = computed(() => props.taskResult.comparison?.confidence_score ?? 0)

const diffs = computed(() => props.taskResult.comparison?.differences || [])
const missingItems = computed(() => props.taskResult.comparison?.missing_items || [])

const diffCount = computed(() => {
  return diffs.value.filter((d: any) => {
    const text = typeof d === 'string' ? d : (d.description || '')
    return text && !(text.includes('一致') && text.includes('未发现'))
  }).length
})

const missingCount = computed(() => missingItems.value.filter((m: any) => m.description).length)

const projectName = computed(() => {
  const bid = props.taskResult.bid_info
  return bid?.vendor_name ? `${bid.vendor_name}采购项目` : '未命名项目'
})

const vendor = computed(() => props.taskResult.bid_info?.vendor_name || props.taskResult.contract_info?.vendor_name || '—')
const bidAmount = computed(() => Number(props.taskResult.bid_info?.total_amount) || 0)
const contractAmount = computed(() => Number(props.taskResult.contract_info?.total_amount) || 0)
const bidDays = computed(() => Number(props.taskResult.bid_info?.delivery_days) || 0)
const contractDays = computed(() => Number(props.taskResult.contract_info?.delivery_days) || 0)

const validDiffs = computed(() => {
  return diffs.value.filter((d: any) => {
    const text = typeof d === 'string' ? d : (d.description || '')
    return text && !(text.includes('一致') && text.includes('未发现'))
  })
})

const validMissing = computed(() => {
  return missingItems.value.filter((m: any) => m.description)
})

const tokenUsage = computed(() => props.taskResult.token_usage)
const tokenTotal = computed(() => tokenUsage.value?.total_tokens || 0)
const modelName = computed(() => props.taskResult.model_name || '—')
const duration = computed(() => {
  const sec = props.taskResult.processing_seconds
  if (sec === undefined || sec === null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s > 0 ? `${m} 分 ${s} 秒` : `${m} 分`
})

function formatRiskLevel(val: string): string {
  const map: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险', safe: '安全' }
  return map[String(val).toLowerCase()] || val
}

function riskClass(val: string): string {
  const v = String(val).toLowerCase()
  if (v === 'high') return 'risk-high'
  if (v === 'medium') return 'risk-medium'
  if (v === 'low') return 'risk-low'
  return 'risk-safe'
}

function detectRiskLevel(text: string): 'high' | 'medium' | 'low' {
  const t = text.toLowerCase()
  if (t.includes('金额') || t.includes('总价') || t.includes('供应商') || t.includes('缺失') || t.includes('违约')) return 'high'
  if (t.includes('有效期') || t.includes('付款') || t.includes('交期') || t.includes('交付') || t.includes('工期')) return 'medium'
  return 'low'
}

function getDiffTitle(item: any): string {
  if (typeof item === 'string') return '条款差异'
  const text = item.description || ''
  if (text.includes('：')) return text.split('：')[0]
  return item.type || '条款差异'
}

function getDiffDescription(item: any): string {
  if (typeof item === 'string') return item
  const text = item.description || ''
  if (text.includes('：')) return text.split('：').slice(1).join('：')
  return text
}

function getDiffRiskLevel(item: any): 'high' | 'medium' | 'low' {
  if (typeof item === 'string') return detectRiskLevel(item)
  const text = (item.description || '') + (item.risk_comment || '')
  return detectRiskLevel(text)
}

function getDiffRiskLabel(level: string): string {
  const map: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' }
  return map[level] || '低风险'
}

function formatCurrency(n: number): string {
  return n ? `¥${n.toLocaleString()}` : '—'
}
</script>

<template>
  <div class="batch-report-body">
    <div class="report-title">智能合规审查报告</div>
    <div class="report-subtitle">Intelligent Compliance Review Report</div>
    <div class="report-meta">
      生成时间：{{ taskResult.created_at || '—' }}
      <span v-if="creatorName">&nbsp;|&nbsp;检测人员：{{ creatorName }}{{ creatorEmpId ? ` (${creatorEmpId})` : '' }}</span>
    </div>

    <!-- 状态概览 -->
    <div class="status-bar">
      <div class="status-item">
        <span class="status-label">风险定级</span>
        <span class="status-value risk-tag" :class="riskClass(riskLevel)">
          {{ formatRiskLevel(riskLevel) }}
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">全局置信度</span>
        <span class="status-value" :style="{ color: confidenceScore >= 0.8 ? '#10b981' : confidenceScore >= 0.5 ? '#f59e0b' : '#ef4444' }">
          {{ Math.round(confidenceScore * 100) }}%
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">差异项</span>
        <span class="status-value status-danger">{{ diffCount }} 项</span>
      </div>
      <div class="status-item">
        <span class="status-label">缺失项</span>
        <span class="status-value status-warning">{{ missingCount }} 项</span>
      </div>
      <div class="status-item status-item--stack">
        <span class="status-label">算力消耗</span>
        <span class="status-value">
          {{ tokenTotal.toLocaleString('zh-CN') }} Tokens
          <span v-if="tokenUsage" class="token-breakdown">
            输入 {{ tokenUsage.prompt_tokens.toLocaleString('zh-CN') }} / 输出 {{ tokenUsage.completion_tokens.toLocaleString('zh-CN') }}
          </span>
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">底层模型</span>
        <span class="status-value status-muted">{{ modelName }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">执行耗时</span>
        <span class="status-value status-muted">{{ duration }}</span>
      </div>
    </div>

    <!-- 全局比对概览 -->
    <div class="section">
      <div class="section-title">全局比对概览</div>
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">项目名称</div>
          <div class="summary-value">{{ projectName }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">供应商</div>
          <div class="summary-value">{{ vendor }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">中标金额</div>
          <div class="summary-value">{{ formatCurrency(bidAmount) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">合同金额</div>
          <div class="summary-value">{{ formatCurrency(contractAmount) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">中标交期</div>
          <div class="summary-value">{{ bidDays ? `${bidDays} 天` : '—' }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">合同交期</div>
          <div class="summary-value">{{ contractDays ? `${contractDays} 天` : '—' }}</div>
        </div>
      </div>
    </div>

    <!-- 差异条款 -->
    <div v-if="validDiffs.length > 0" class="section">
      <div class="section-title">
        差异条款（{{ diffCount }} 项）
      </div>
      <div
        v-for="(item, idx) in validDiffs"
        :key="'diff-' + idx"
        class="diff-card"
      >
        <div class="diff-card-header">
          <div class="diff-card-title">{{ getDiffTitle(item) }}</div>
          <span
            class="risk-badge"
            :class="'risk-' + getDiffRiskLevel(item)"
          >
            {{ getDiffRiskLabel(getDiffRiskLevel(item)) }}
          </span>
        </div>
        <div class="diff-card-body">
          <div class="diff-source-row">
            <div class="diff-source-block">
              <div class="diff-source-label">采购结果约定</div>
              <div class="diff-source-text diff-source-text--bid">
                {{ typeof item === 'string' ? '—' : (item.original_text || '—') }}
              </div>
            </div>
            <div class="diff-source-block">
              <div class="diff-source-label">合同约定</div>
              <div class="diff-source-text diff-source-text--contract">
                {{ typeof item === 'string' ? '—' : (item.contract_text || '—') }}
              </div>
            </div>
          </div>
          <div class="diff-desc">
            <strong>差异描述：</strong>{{ getDiffDescription(item) }}
          </div>
          <div v-if="typeof item !== 'string' && item.risk_comment" class="diff-risk-comment">
            <strong>风险提示：</strong>{{ item.risk_comment }}
          </div>
          <div v-if="typeof item !== 'string' && item.suggested_amendment" class="diff-suggestion">
            <strong>建议修改为：</strong>{{ item.suggested_amendment }}
          </div>
        </div>
      </div>
    </div>

    <!-- 缺失条款 -->
    <div v-if="validMissing.length > 0" class="section">
      <div class="section-title">
        缺失条款（{{ missingCount }} 项）
      </div>
      <div
        v-for="(item, idx) in validMissing"
        :key="'missing-' + idx"
        class="diff-card diff-card--missing"
      >
        <div class="diff-card-header">
          <div class="diff-card-title">{{ item.clause_name || '缺失条款' }}</div>
          <span class="risk-badge risk-high">高风险</span>
        </div>
        <div class="diff-card-body">
          <div class="diff-source-row">
            <div class="diff-source-block">
              <div class="diff-source-label">采购结果约定</div>
              <div class="diff-source-text diff-source-text--bid">
                {{ item.original_text || '（采购结果中有）' }}
              </div>
            </div>
            <div class="diff-source-block">
              <div class="diff-source-label">合同约定</div>
              <div class="diff-source-text diff-source-text--contract">
                {{ item.contract_text || '（合同中未找到）' }}
              </div>
            </div>
          </div>
          <div class="diff-desc">
            <strong>缺失描述：</strong>{{ item.description }}
          </div>
          <div v-if="item.risk_comment" class="diff-risk-comment">
            <strong>风险提示：</strong>{{ item.risk_comment }}
          </div>
          <div v-if="item.suggested_amendment" class="diff-suggestion">
            <strong>建议修改为：</strong>{{ item.suggested_amendment }}
          </div>
        </div>
      </div>
    </div>

    <!-- 无差异提示 -->
    <div v-if="validDiffs.length === 0 && validMissing.length === 0" class="section">
      <div class="no-diff-box">
        未检测到实质性差异或缺失条款，合同与采购结果基本一致。
      </div>
    </div>
  </div>
</template>

<style scoped>
.batch-report-body {
  background: #fff;
  padding: 24px 28px;
  font-family: 'Microsoft YaHei', 'PingFang SC', SimSun, sans-serif !important;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(30, 58, 138, 0.06);
  max-width: 100%;
}

.batch-report-body * {
  font-family: 'Microsoft YaHei', 'PingFang SC', SimSun, sans-serif !important;
}

.report-title {
  font-size: 24px;
  font-weight: 700;
  text-align: center;
  color: #1e3a8a;
  margin-bottom: 4px;
  letter-spacing: 2px;
}

.report-subtitle {
  font-size: 12px;
  color: #64748b;
  text-align: center;
  margin-bottom: 8px;
  letter-spacing: 1px;
}

.report-meta {
  font-size: 12px;
  color: #64748b;
  text-align: center;
  margin-bottom: 16px;
}

/* 状态栏 */
.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 20px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 18px;
  margin-bottom: 18px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-label {
  color: #64748b;
  font-weight: 500;
}

.status-value {
  font-weight: 700;
  color: #1e293b;
}

.status-danger {
  color: #dc2626;
}

.status-warning {
  color: #d97706;
}

.status-muted {
  color: #64748b;
  font-weight: 600;
}

.status-item--stack {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.token-breakdown {
  display: block;
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
  margin-top: 1px;
}

.risk-tag {
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  color: #fff;
}

.risk-high {
  background: #dc2626;
}

.risk-medium {
  background: #f59e0b;
  color: #fff;
}

.risk-low {
  background: #3b82f6;
  color: #fff;
}

.risk-safe {
  background: #10b981;
  color: #fff;
}

/* 区块 */
.section {
  margin-bottom: 22px;
  break-inside: avoid;
  page-break-inside: avoid;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e40af;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  break-after: avoid;
  page-break-after: avoid;
}

/* 概览网格 */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px 24px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 18px 20px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.summary-value {
  font-size: 14px;
  color: #1e293b;
  font-weight: 600;
}

/* 差异卡片 */
.diff-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #ef4444;
  border-radius: 10px;
  margin-bottom: 14px;
  overflow: hidden;
}

.diff-card--missing {
  border-left-color: #f59e0b;
}

.diff-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #f1f5f9;
  flex-wrap: wrap;
}

.diff-card-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.risk-badge {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
}

.diff-card-body {
  padding: 14px 16px;
}

.diff-source-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}

.diff-source-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.diff-source-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.diff-source-text {
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
  word-break: break-word;
  min-height: 40px;
}

.diff-source-text--bid {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.diff-source-text--contract {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #7f1d1d;
}

.diff-desc {
  font-size: 13px;
  color: #334155;
  line-height: 1.7;
  margin-bottom: 8px;
  word-break: break-word;
}

.diff-risk-comment {
  font-size: 13px;
  color: #991b1b;
  line-height: 1.7;
  margin-bottom: 8px;
  background: #fef2f2;
  border-radius: 6px;
  padding: 8px 12px;
  word-break: break-word;
}

.diff-suggestion {
  font-size: 13px;
  color: #166534;
  line-height: 1.7;
  background: #f0fdf4;
  border-radius: 6px;
  padding: 8px 12px;
  word-break: break-word;
}

.no-diff-box {
  text-align: center;
  padding: 30px;
  color: #64748b;
  font-size: 14px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px dashed #e2e8f0;
}

@media print {
  .batch-report-body {
    box-shadow: none;
    padding: 0;
  }
}
</style>
