<script setup lang="ts">
import { computed } from 'vue'
import { WarningFilled, Warning } from '@element-plus/icons-vue'
import type { FinancialInfo, BidInfo, ContractInfo } from '@/types/api'

const props = defineProps<{
  financialInfo?: FinancialInfo
  contractTotalAmount?: number | string
  bidInfo?: BidInfo
  contractInfo?: ContractInfo
}>()

const financialSummary = computed(() => {
  const fi = props.financialInfo
  const contractTotal = props.contractTotalAmount
  return {
    totalAmount: fi?.total_amount || (typeof contractTotal === 'number' ? contractTotal : 0),
    warrantyRatio: fi?.warranty_ratio || 0,
    nodeCount: fi?.payment_nodes?.length || 0,
  }
})

const financialNodes = computed(() => {
  const nodes = props.financialInfo?.payment_nodes || []
  const total = financialSummary.value.totalAmount || 1
  return nodes.map((node) => {
    const ratio = node.percentage || 0
    const amount = node.amount || ratio * total
    const nodeName = node.node_name || ''
    let status: 'success' | 'warning' | 'error' = 'success'
    let warningReason = ''

    if (nodeName.includes('预付') && ratio > 0.5) {
      status = 'error'
      warningReason = '预付款比例过高（>50%），存在资金占用风险'
    } else if (nodeName.includes('质保') && ratio < 0.05) {
      status = 'warning'
      warningReason = '质保金比例偏低（<5%），建议留存不低于 5%'
    } else if (ratio > 0.6) {
      status = 'warning'
      warningReason = '单节点付款比例过高（>60%），建议分期支付以控制风险'
    }

    return { ...node, node_name: nodeName, ratio, amount, status, warningReason }
  })
})

const hasFinancialWarning = computed(() =>
  financialNodes.value.some((n) => n.status !== 'success')
)

// 交付履约数据
const bidDeliveryDays = computed(() => {
  const d = props.bidInfo?.delivery_days
  if (typeof d === 'number') return d
  if (typeof d === 'string' && d.trim() !== '') return Number(d) || 0
  return 0
})

const contractDeliveryDays = computed(() => {
  const d = props.contractInfo?.delivery_days
  if (typeof d === 'number') return d
  if (typeof d === 'string' && d.trim() !== '') return Number(d) || 0
  return 0
})

const deliveryDiffDays = computed(() => contractDeliveryDays.value - bidDeliveryDays.value)

const hasDeliveryInfo = computed(() => {
  return (
    (props.bidInfo?.delivery_days !== undefined && props.bidInfo?.delivery_days !== '') ||
    (props.contractInfo?.delivery_days !== undefined && props.contractInfo?.delivery_days !== '')
  )
})
</script>

<template>
  <div id="section-finance" class="payment-timeline">
    <div class="financial-header">
      <div class="financial-title">财务付款履约路线图</div>
      <div class="financial-subtitle">
        基于合同文本提取的付款节点与资金安排，供财务人员参考
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：财务摘要卡片 -->
      <el-col :xs="24" :md="8">
        <div class="financial-summary-card">
          <div class="summary-title">财务摘要</div>
          <div class="summary-body">
            <div class="summary-item">
              <span class="summary-label">合同总标的额</span>
              <span class="summary-value highlight">
                ¥ {{ financialSummary.totalAmount.toLocaleString('zh-CN') }}
              </span>
            </div>
            <div class="summary-item">
              <span class="summary-label">质保金留存比例</span>
              <span
                class="summary-value"
                :class="{
                  'risk-text': financialSummary.warrantyRatio < 0.05,
                }"
              >
                {{ (financialSummary.warrantyRatio * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="summary-item">
              <span class="summary-label">付款节点数</span>
              <span class="summary-value">{{ financialSummary.nodeCount }} 个</span>
            </div>
            <div v-if="hasFinancialWarning" class="summary-warning">
              <el-icon><WarningFilled /></el-icon>
              <span>检测到异常付款节点，请留意右侧时间轴标红/标橙项</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧：付款节点时间轴 -->
      <el-col :xs="24" :md="16">
        <div class="financial-timeline-card">
          <div class="timeline-title">付款节点时间轴</div>
          <div v-if="financialNodes.length" class="timeline-body">
            <el-steps direction="vertical" :active="999" finish-status="success">
              <el-step v-for="(node, idx) in financialNodes" :key="idx">
                <template #title>
                  <span
                    class="node-title"
                    :class="{
                      'node-warning': node.status === 'warning',
                      'node-error': node.status === 'error',
                    }"
                  >
                    {{ node.node_name }}
                  </span>
                  <el-tag
                    v-if="node.status !== 'success'"
                    :type="node.status"
                    size="small"
                    class="node-tag"
                  >
                    {{ node.status === 'error' ? '高风险' : '警告' }}
                  </el-tag>
                </template>
                <template #description>
                  <div class="node-desc">
                    <div class="node-row">
                      <span class="node-label">付款占比</span>
                      <span
                        class="node-value"
                        :class="{
                          'node-warning': node.status === 'warning',
                          'node-error': node.status === 'error',
                        }"
                      >
                        {{ (node.ratio * 100).toFixed(1) }}%
                      </span>
                    </div>
                    <div class="node-row">
                      <span class="node-label">预计金额</span>
                      <span class="node-value">
                        ¥ {{ node.amount.toLocaleString('zh-CN') }}
                      </span>
                    </div>
                    <div class="node-row">
                      <span class="node-label">付款条件</span>
                      <span class="node-value condition">
                        {{ node.condition || '—' }}
                      </span>
                    </div>
                    <div v-if="node.warningReason" class="node-reason">
                      <el-icon><Warning /></el-icon>
                      {{ node.warningReason }}
                    </div>
                  </div>
                </template>
              </el-step>
            </el-steps>
          </div>
          <el-empty v-else description="未提取到财务付款节点信息" />

          <!-- 交付履约节点 -->
          <div class="delivery-divider"></div>
          <div class="timeline-title">交付履约节点</div>
          <div v-if="hasDeliveryInfo" class="timeline-body delivery-timeline">
            <el-steps direction="vertical" :active="999" finish-status="success">
              <el-step>
                <template #title>
                  <span class="node-title">项目启动 / 合同生效</span>
                </template>
                <template #description>
                  <div class="node-desc">
                    <div class="node-row">
                      <span class="node-label">基准日期</span>
                      <span class="node-value">合同签署日（T+0）</span>
                    </div>
                  </div>
                </template>
              </el-step>
              <el-step>
                <template #title>
                  <span class="node-title">采招承诺交付</span>
                </template>
                <template #description>
                  <div class="node-desc">
                    <div class="node-row">
                      <span class="node-label">承诺交期</span>
                      <span class="node-value">{{ bidDeliveryDays }} 天</span>
                    </div>
                  </div>
                </template>
              </el-step>
              <el-step>
                <template #title>
                  <span
                    class="node-title"
                    :class="{
                      'node-warning': deliveryDiffDays !== 0,
                    }"
                  >
                    合同约定交付
                  </span>
                  <el-tag
                    v-if="deliveryDiffDays !== 0"
                    :type="deliveryDiffDays > 0 ? 'warning' : 'success'"
                    size="small"
                    class="node-tag"
                  >
                    {{ deliveryDiffDays > 0 ? '延期' : '提前' }}
                  </el-tag>
                </template>
                <template #description>
                  <div class="node-desc">
                    <div class="node-row">
                      <span class="node-label">约定交期</span>
                      <span
                        class="node-value"
                        :class="{
                          'node-warning': deliveryDiffDays !== 0,
                        }"
                      >
                        {{ contractDeliveryDays }} 天
                      </span>
                    </div>
                    <div v-if="deliveryDiffDays !== 0" class="node-reason">
                      <el-icon><Warning /></el-icon>
                      合同约定的交付天数（{{ contractDeliveryDays }} 天）与采招承诺（{{ bidDeliveryDays }} 天）相差 {{ Math.abs(deliveryDiffDays) }} 天
                    </div>
                  </div>
                </template>
              </el-step>
            </el-steps>
          </div>
          <el-empty v-else description="未提取到交付履约信息" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.payment-timeline {
  padding: 20px;
  background: #fff;
  min-height: 480px;
}

.financial-header {
  text-align: center;
  margin-bottom: 20px;
}

.financial-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e3a8a;
  letter-spacing: 1px;
}

.financial-subtitle {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.financial-summary-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 16px;
  height: 100%;
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  border-left: 4px solid #2563eb;
  padding-left: 10px;
  margin-bottom: 12px;
}

.summary-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.summary-label {
  color: #64748b;
  font-weight: 500;
}

.summary-value {
  color: #1e293b;
  font-weight: 600;
}

.summary-value.highlight {
  font-size: 15px;
  color: #2563eb;
}

.summary-warning {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #b45309;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.risk-text {
  color: #dc2626;
  font-weight: 600;
}

.financial-timeline-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 16px;
  height: 100%;
}

.timeline-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  border-left: 4px solid #2563eb;
  padding-left: 10px;
  margin-bottom: 16px;
}

.timeline-body {
  max-height: 520px;
  overflow-y: auto;
}

.node-title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}

.node-title.node-warning {
  color: #d97706;
}

.node-title.node-error {
  color: #dc2626;
}

.node-tag {
  margin-left: 8px;
}

.node-desc {
  margin-top: 6px;
}

.node-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}

.node-label {
  color: #64748b;
  font-weight: 500;
  min-width: 64px;
}

.node-value {
  color: #1e293b;
  font-weight: 600;
}

.node-value.node-warning {
  color: #d97706;
}

.node-value.node-error {
  color: #dc2626;
}

.node-value.condition {
  font-weight: 400;
  color: #475569;
}

.node-reason {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-top: 6px;
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  padding: 6px 8px;
  border-radius: 4px;
}

/* 交付履约节点分隔 */
.delivery-divider {
  height: 1px;
  background: #e2e8f0;
  margin: 20px 0 16px;
}

.delivery-timeline {
  max-height: 360px;
}
</style>
