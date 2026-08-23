<script setup lang="ts">
import type { BidInfo, ContractInfo } from '@/types/api'

const props = defineProps<{
  bidInfo?: BidInfo
  contractInfo?: ContractInfo
}>()

const fields = [
  { key: 'vendor_name' as const, label: '供应商名称' },
  { key: 'total_amount' as const, label: '总金额（元）' },
  { key: 'delivery_days' as const, label: '交期天数' },
]

const penaltyFields = [
  { key: 'delay_daily_rate' as const, label: '逾期日罚息比例' },
  { key: 'penalty_cap_rate' as const, label: '累计违约金上限' },
  { key: 'termination_penalty_rate' as const, label: '解约赔偿比例' },
]

function fmtPenalty(value: number | string | undefined): string {
  if (!value) return '—'
  const v = Number(value)
  if (!v) return '—'
  const pct = v * 100
  if (pct >= 1) return `${pct.toFixed(1)}%`
  if (pct >= 0.1) return `${pct.toFixed(2)}%`
  return `${pct.toFixed(3)}%`
}
</script>

<template>
  <div id="section-history" class="contract-compare">
    <!-- 采购结果关键信息 -->
    <div class="report-section">
      <div class="section-title">采购结果（Bid）关键信息</div>
      <el-descriptions :column="2" border>
        <el-descriptions-item
          v-for="f in fields"
          :key="`bid-${f.key}`"
          :label="f.label"
          label-class-name="report-label"
        >
          {{ bidInfo?.[f.key] ?? '—' }}
        </el-descriptions-item>
        <el-descriptions-item
          v-for="f in penaltyFields"
          :key="`bid-${f.key}`"
          :label="f.label"
          label-class-name="report-label"
        >
          {{ fmtPenalty(bidInfo?.[f.key]) }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 合同关键信息 -->
    <div class="report-section">
      <div class="section-title">正式合同（Contract）关键信息</div>
      <el-descriptions :column="2" border>
        <el-descriptions-item
          v-for="f in fields"
          :key="`contract-${f.key}`"
          :label="f.label"
          label-class-name="report-label"
        >
          <span
            :class="{
              'risk-text':
                bidInfo?.[f.key] !== undefined &&
                contractInfo?.[f.key] !== undefined &&
                bidInfo[f.key] !== contractInfo[f.key],
            }"
          >
            {{ contractInfo?.[f.key] ?? '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item
          v-for="f in penaltyFields"
          :key="`contract-${f.key}`"
          :label="f.label"
          label-class-name="report-label"
        >
          <span
            :class="{
              'risk-text':
                Number(bidInfo?.[f.key] || 0) > 0 &&
                Number(contractInfo?.[f.key] || 0) >= 0 &&
                Math.abs(Number(bidInfo?.[f.key]) - Number(contractInfo?.[f.key])) > 0.0001,
            }"
          >
            {{ fmtPenalty(contractInfo?.[f.key]) }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<style scoped>
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

.risk-text {
  color: #dc2626;
  font-weight: 600;
}

:deep(.report-label) {
  font-weight: 600;
  color: #475569;
  background: #f1f5f9;
}
</style>
