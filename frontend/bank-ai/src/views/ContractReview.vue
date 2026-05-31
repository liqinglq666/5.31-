<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back,
  UploadFilled,
  Document,
  Cpu,
  Loading,
  CircleCheck,
  CircleClose,
  Warning,
  Monitor,
} from '@element-plus/icons-vue'
import { submitContractReview, getContractReviewStatus, getAvailableModels } from '@/api'
import type { ModelItem } from '@/types/api'
import AppHeader from '@/components/AppHeader.vue'

const router = useRouter()

// ---------------------------------------------------------------------------
// 文件上传状态
// ---------------------------------------------------------------------------
const bidFile = ref<File | null>(null)
const contractFile = ref<File | null>(null)
const bidFileName = computed(() => bidFile.value?.name || '')
const contractFileName = computed(() => contractFile.value?.name || '')

const handleBidChange = (uploadFile: any) => {
  bidFile.value = uploadFile.raw
}

const handleContractChange = (uploadFile: any) => {
  contractFile.value = uploadFile.raw
}

const beforeUpload = (file: File) => {
  const validTypes = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  ]
  const isValid = validTypes.includes(file.type) || file.name.endsWith('.pdf') || file.name.endsWith('.doc') || file.name.endsWith('.docx')
  if (!isValid) {
    ElMessage.error('仅支持 PDF、Word 格式文件')
    return false
  }
  const isLt20M = file.size / 1024 / 1024 < 20
  if (!isLt20M) {
    ElMessage.error('文件大小不能超过 20MB')
    return false
  }
  return false // 阻止自动上传，手动触发
}

// ---------------------------------------------------------------------------
// 模型选择
// ---------------------------------------------------------------------------
const availableModels = ref<ModelItem[]>([])
const selectedModel = ref<string>('')
const modelLoading = ref(false)

const modelGroups = computed(() => {
  const groups: Record<string, ModelItem[]> = {}
  availableModels.value.forEach((m) => {
    if (!groups[m.provider]) groups[m.provider] = []
    groups[m.provider]!.push(m)
  })
  return Object.entries(groups).map(([provider, models]) => ({
    provider,
    label: providerNameMap[provider] || provider,
    models,
  }))
})

const providerNameMap: Record<string, string> = {
  zhipu: '智谱 AI',
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  moonshot: 'Moonshot',
  doubao: '豆包',
  minimax: 'MiniMax',
  openai: 'OpenAI',
}

const fetchModels = async () => {
  modelLoading.value = true
  try {
    const res = await getAvailableModels()
    availableModels.value = res.data.data || []
    const recommended = availableModels.value.find((m) => m.recommended)
    selectedModel.value = recommended?.id || availableModels.value[0]?.id || ''
  } catch (_err) {
    ElMessage.error('加载模型列表失败')
  } finally {
    modelLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 提交流程
// ---------------------------------------------------------------------------
const isSubmitting = ref(false)
const taskId = ref('')
const taskStatus = ref('')
const taskResult = ref<any>(null)
const taskError = ref('')
const elapsedSeconds = ref(0)
let pollTimer: number | null = null
let elapsedTimer: number | null = null

const canSubmit = computed(() => {
  return !!bidFile.value && !!contractFile.value && !!selectedModel.value && !isSubmitting.value
})

const clearTimers = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

const handleSubmit = async () => {
  if (!bidFile.value || !contractFile.value) {
    ElMessage.warning('请上传采购结果文件和正式合同文件')
    return
  }

  const formData = new FormData()
  formData.append('bid_file', bidFile.value)
  formData.append('contract_file', contractFile.value)
  if (selectedModel.value) {
    formData.append('model_id', selectedModel.value)
  }

  isSubmitting.value = true
  taskStatus.value = 'processing'
  taskResult.value = null
  taskError.value = ''
  elapsedSeconds.value = 0
  clearTimers()

  try {
    const res = await submitContractReview(formData)
    taskId.value = res.data.data.task_id
    ElMessage.success('审查任务已提交')

    // 启动计时器
    elapsedTimer = window.setInterval(() => {
      elapsedSeconds.value++
    }, 1000)

    // 轮询
    pollTimer = window.setInterval(async () => {
      try {
        const statusRes = await getContractReviewStatus(taskId.value)
        const data = statusRes.data.data
        taskStatus.value = data.status

        if (data.status === 'completed') {
          clearTimers()
          taskResult.value = data.result
          isSubmitting.value = false
          ElMessage.success('审查完成')
        } else if (data.status === 'failed') {
          clearTimers()
          taskError.value = data.error_message || '审查失败'
          isSubmitting.value = false
          ElMessage.error(taskError.value)
        }
      } catch (_err) {
        clearTimers()
        isSubmitting.value = false
        ElMessage.error('轮询任务状态时发生网络错误')
      }
    }, 3000)
  } catch (_err) {
    isSubmitting.value = false
    ElMessage.error('任务提交失败')
  }
}

// ---------------------------------------------------------------------------
// 结果展示辅助
// ---------------------------------------------------------------------------
const riskLevelClass = computed(() => {
  const level = taskResult.value?.stage5_supervisor?.risk_level || ''
  if (level === 'high') return 'risk-high'
  if (level === 'medium') return 'risk-medium'
  return 'risk-low'
})

const riskLevelText = computed(() => {
  const level = taskResult.value?.stage5_supervisor?.risk_level || ''
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  return '低风险'
})

const formattedJson = computed(() => {
  if (!taskResult.value) return ''
  return JSON.stringify(taskResult.value, null, 2)
})

onMounted(() => {
  fetchModels()
})

onUnmounted(() => {
  clearTimers()
})
</script>

<template>
  <div class="review-page">
    <AppHeader />

    <div class="review-container">
      <!-- 顶部返回与标题 -->
      <div class="review-header">
        <el-button text class="back-btn" @click="router.push('/')">
          <el-icon><Back /></el-icon>
          返回中台
        </el-button>
        <div class="title-area">
          <h1 class="main-title">
            <el-icon class="title-icon"><Monitor /></el-icon>
            智契全链路合同审查
          </h1>
          <p class="sub-title">
            MoE 多智能体协同 · 物理引擎预检 · CoVe 链式核查
          </p>
        </div>
      </div>

      <div class="review-body">
        <!-- 左侧：上传与配置 -->
        <div class="upload-section">
          <el-card class="upload-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><UploadFilled /></el-icon>
                <span>文件上传</span>
              </div>
            </template>

            <div class="upload-list">
              <!-- 采购结果文件 -->
              <div class="upload-item">
                <div class="upload-label">
                  <el-icon><Document /></el-icon>
                  <span>采购结果公告</span>
                  <el-tag size="small" type="primary">必传</el-tag>
                </div>
                <el-upload
                  drag
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleBidChange"
                  :before-upload="beforeUpload"
                  accept=".pdf,.doc,.docx"
                  class="upload-box"
                >
                  <el-icon class="upload-icon"><UploadFilled /></el-icon>
                  <div class="upload-text">
                    <span v-if="bidFileName" class="file-name">{{ bidFileName }}</span>
                    <span v-else>拖拽文件到此处，或<em>点击上传</em></span>
                  </div>
                  <template #tip>
                    <div class="upload-tip">支持 PDF、Word，最大 20MB</div>
                  </template>
                </el-upload>
              </div>

              <!-- 正式合同文件 -->
              <div class="upload-item">
                <div class="upload-label">
                  <el-icon><Document /></el-icon>
                  <span>正式合同文本</span>
                  <el-tag size="small" type="primary">必传</el-tag>
                </div>
                <el-upload
                  drag
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleContractChange"
                  :before-upload="beforeUpload"
                  accept=".pdf,.doc,.docx"
                  class="upload-box"
                >
                  <el-icon class="upload-icon"><UploadFilled /></el-icon>
                  <div class="upload-text">
                    <span v-if="contractFileName" class="file-name">{{ contractFileName }}</span>
                    <span v-else>拖拽文件到此处，或<em>点击上传</em></span>
                  </div>
                  <template #tip>
                    <div class="upload-tip">支持 PDF、Word，最大 20MB</div>
                  </template>
                </el-upload>
              </div>
            </div>

            <!-- 模型选择 -->
            <div class="model-select-row">
              <div class="upload-label">
                <el-icon><Cpu /></el-icon>
                <span>审查模型</span>
              </div>
              <el-select
                v-model="selectedModel"
                placeholder="请选择审查模型"
                class="model-select"
                :loading="modelLoading"
              >
                <el-option-group
                  v-for="group in modelGroups"
                  :key="group.provider"
                  :label="group.label"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.id"
                    :label="`${model.name} ${model.recommended ? '(推荐)' : ''}`"
                    :value="model.id"
                  >
                    <div class="model-option">
                      <span>{{ model.name }}</span>
                      <el-tag v-if="model.recommended" size="small" type="success">推荐</el-tag>
                      <span class="model-version">{{ model.version }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
            </div>

            <!-- 提交按钮 -->
            <el-button
              type="primary"
              size="large"
              class="submit-btn"
              :disabled="!canSubmit"
              :loading="isSubmitting"
              @click="handleSubmit"
            >
              <el-icon v-if="!isSubmitting"><Monitor /></el-icon>
              {{ isSubmitting ? '审查进行中...' : '启动全链路审查' }}
            </el-button>
          </el-card>

          <!-- 状态卡片 -->
          <el-card v-if="isSubmitting || taskStatus === 'completed' || taskStatus === 'failed'" class="status-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><Loading /></el-icon>
                <span>任务状态</span>
                <el-tag :type="taskStatus === 'completed' ? 'success' : taskStatus === 'failed' ? 'danger' : 'warning'" size="small">
                  {{ taskStatus === 'completed' ? '已完成' : taskStatus === 'failed' ? '失败' : '执行中' }}
                </el-tag>
              </div>
            </template>

            <div class="status-body">
              <div class="status-row">
                <span class="status-label">Task ID</span>
                <span class="status-value task-id">{{ taskId }}</span>
              </div>
              <div class="status-row">
                <span class="status-label">已耗时</span>
                <span class="status-value">{{ elapsedSeconds }} 秒</span>
              </div>
              <div v-if="taskStatus === 'processing'" class="status-hint">
                <el-icon class="spin-icon"><Loading /></el-icon>
                多智能体正在协同审查，请稍候...
              </div>
              <div v-else-if="taskStatus === 'completed'" class="status-hint success">
                <el-icon><CircleCheck /></el-icon>
                审查已完成，结果见右侧报告面板
              </div>
              <div v-else-if="taskStatus === 'failed'" class="status-hint error">
                <el-icon><CircleClose /></el-icon>
                {{ taskError }}
              </div>
            </div>
          </el-card>
        </div>

        <!-- 右侧：审查报告 -->
        <div class="report-section">
          <el-card class="report-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><Document /></el-icon>
                <span>审查报告</span>
                <el-tag v-if="taskResult" :type="riskLevelClass.replace('risk-', '')" size="small" class="risk-tag">
                  {{ riskLevelText }}
                </el-tag>
              </div>
            </template>

            <div v-if="!taskResult" class="report-empty">
              <el-icon class="empty-icon"><Document /></el-icon>
              <p>暂无审查报告</p>
              <p class="empty-sub">请在左侧上传文件并启动审查</p>
            </div>

            <div v-else class="report-content">
              <!-- 综述 -->
              <div class="report-overview">
                <div class="overview-item">
                  <span class="overview-label">风险等级</span>
                  <el-tag :class="riskLevelClass" size="large" effect="dark">
                    {{ riskLevelText }}
                  </el-tag>
                </div>
                <div class="overview-item">
                  <span class="overview-label">置信度</span>
                  <span class="overview-value">
                    {{ (taskResult.stage5_supervisor?.confidence_score * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="overview-item">
                  <span class="overview-label">审查意见</span>
                  <span class="overview-value comment">
                    {{ taskResult.stage5_supervisor?.review_comments || '无' }}
                  </span>
                </div>
              </div>

              <!-- 各阶段详情 -->
              <el-collapse class="report-collapse">
                <el-collapse-item title="Stage 1 · 文档解析" name="stage1">
                  <div class="stage-content">
                    <p>采购公告字符数：{{ taskResult.stage1_ingestion?.bid_chars || 0 }}</p>
                    <p>合同文本字符数：{{ taskResult.stage1_ingestion?.contract_chars || 0 }}</p>
                  </div>
                </el-collapse-item>

                <el-collapse-item title="Stage 2 · 记忆层索引" name="stage2">
                  <div class="stage-content">
                    <p>采购公告 Doc ID：{{ taskResult.stage2_memory?.bid_doc_id || '-' }}</p>
                    <p>合同文本 Doc ID：{{ taskResult.stage2_memory?.contract_doc_id || '-' }}</p>
                    <p>采购插入向量数：{{ taskResult.stage2_memory?.bid_inserted || 0 }}</p>
                    <p>合同插入向量数：{{ taskResult.stage2_memory?.contract_inserted || 0 }}</p>
                  </div>
                </el-collapse-item>

                <el-collapse-item title="Stage 3 · 物理引擎预检" name="stage3">
                  <div class="stage-content">
                    <p>Token 消耗：{{ taskResult.stage3_extraction?.token_usage?.total_tokens || 0 }} (Prompt: {{ taskResult.stage3_extraction?.token_usage?.prompt_tokens || 0 }} / Completion: {{ taskResult.stage3_extraction?.token_usage?.completion_tokens || 0 }})</p>
                    <div v-if="taskResult.stage3_extraction?.physical_alerts?.length" class="alert-list">
                      <div v-for="(alert, idx) in taskResult.stage3_extraction.physical_alerts" :key="idx" class="alert-item">
                        <el-icon class="alert-icon"><Warning /></el-icon>
                        {{ alert }}
                      </div>
                    </div>
                    <p v-else>物理引擎无告警</p>
                  </div>
                </el-collapse-item>

                <el-collapse-item title="Stage 4 · Agent 委员会" name="stage4">
                  <div class="stage-content">
                    <p><strong>Agent A（商务专员）</strong></p>
                    <pre class="json-block">{{ JSON.stringify(taskResult.stage4_committee?.agent_a, null, 2) || '[]' }}</pre>
                    <p><strong>Agent B（法务专员）</strong></p>
                    <pre class="json-block">{{ JSON.stringify(taskResult.stage4_committee?.agent_b, null, 2) || '[]' }}</pre>
                  </div>
                </el-collapse-item>

                <el-collapse-item title="Stage 5 · Supervisor CoVe 仲裁" name="stage5">
                  <div class="stage-content">
                    <p><strong>差异项</strong></p>
                    <pre class="json-block">{{ JSON.stringify(taskResult.stage5_supervisor?.differences, null, 2) || '[]' }}</pre>
                    <p><strong>缺失项</strong></p>
                    <pre class="json-block">{{ JSON.stringify(taskResult.stage5_supervisor?.missing_items, null, 2) || '[]' }}</pre>
                    <p><strong>匹配项</strong></p>
                    <pre class="json-block">{{ JSON.stringify(taskResult.stage5_supervisor?.matches, null, 2) || '[]' }}</pre>
                    <p><strong>CoVe 核查记录</strong></p>
                    <div class="cove-box">
                      {{ taskResult.stage5_supervisor?._cove_verification || '无' }}
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>

              <!-- 原始 JSON -->
              <el-divider />
              <el-collapse>
                <el-collapse-item title="原始 JSON 数据" name="raw">
                  <pre class="raw-json">{{ formattedJson }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
          </el-card>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-page {
  min-height: 100vh;
  background: #f7f8fa;
}

.review-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

/* ---------------------------------------------------------------------------
   顶部标题区
   --------------------------------------------------------------------------- */
.review-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.back-btn {
  color: #4e5969;
  font-size: 14px;
}

.back-btn:hover {
  color: #1e3a8a;
}

.title-area {
  flex: 1;
}

.main-title {
  font-size: 22px;
  font-weight: 700;
  color: #1d2129;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  color: #1e3a8a;
  font-size: 26px;
}

.sub-title {
  font-size: 13px;
  color: #86909c;
  margin: 6px 0 0;
  letter-spacing: 0.5px;
}

/* ---------------------------------------------------------------------------
   主体布局
   --------------------------------------------------------------------------- */
.review-body {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 24px;
  align-items: start;
}

@media (max-width: 1024px) {
  .review-body {
    grid-template-columns: 1fr;
  }
}

/* ---------------------------------------------------------------------------
   左侧上传区
   --------------------------------------------------------------------------- */
.upload-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upload-card,
.status-card {
  border-radius: 10px;
  border: none;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.upload-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upload-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.upload-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #4e5969;
}

.upload-label .el-icon {
  color: #86909c;
}

.upload-box :deep(.el-upload-dragger) {
  padding: 20px;
  border-radius: 8px;
  border-color: #dcdfe6;
  transition: border-color 0.2s;
}

.upload-box :deep(.el-upload-dragger:hover) {
  border-color: #1e3a8a;
}

.upload-icon {
  font-size: 32px;
  color: #c9cdd4;
  margin-bottom: 8px;
}

.upload-text {
  font-size: 13px;
  color: #86909c;
}

.upload-text em {
  color: #1e3a8a;
  font-style: normal;
  font-weight: 500;
}

.file-name {
  color: #1d2129;
  font-weight: 500;
}

.upload-tip {
  font-size: 12px;
  color: #c9cdd4;
  margin-top: 4px;
}

/* 模型选择 */
.model-select-row {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.model-select {
  width: 100%;
}

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-version {
  font-size: 12px;
  color: #c9cdd4;
  margin-left: auto;
}

/* 提交按钮 */
.submit-btn {
  width: 100%;
  margin-top: 16px;
  font-size: 15px;
  letter-spacing: 1px;
  border-radius: 8px;
}

/* 状态卡片 */
.status-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-label {
  color: #86909c;
  width: 60px;
  flex-shrink: 0;
}

.status-value {
  color: #1d2129;
  font-weight: 500;
}

.task-id {
  font-family: monospace;
  font-size: 12px;
  color: #4e5969;
  background: #f2f3f5;
  padding: 2px 8px;
  border-radius: 4px;
}

.status-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #4e5969;
  margin-top: 8px;
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 6px;
}

.status-hint.success {
  color: #67c23a;
  background: #f0f9eb;
}

.status-hint.error {
  color: #f56c6c;
  background: #fef0f0;
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------------------------------------------------------------------------
   右侧报告区
   --------------------------------------------------------------------------- */
.report-card {
  border-radius: 10px;
  border: none;
  min-height: 600px;
}

.report-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: #c9cdd4;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.report-empty p {
  font-size: 15px;
  color: #86909c;
  margin: 0;
}

.empty-sub {
  font-size: 13px !important;
  margin-top: 6px !important;
}

/* 综述 */
.report-overview {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  background: #f7f8fa;
  border-radius: 8px;
  margin-bottom: 20px;
}

.overview-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.overview-label {
  font-size: 13px;
  color: #86909c;
  width: 70px;
  flex-shrink: 0;
  margin-top: 2px;
}

.overview-value {
  font-size: 14px;
  color: #1d2129;
  font-weight: 500;
  flex: 1;
}

.overview-value.comment {
  color: #4e5969;
  font-weight: 400;
  line-height: 1.6;
}

/* 风险标签 */
.risk-high {
  background: #fef0f0 !important;
  color: #f56c6c !important;
  border-color: #fde2e2 !important;
}

.risk-medium {
  background: #fdf6ec !important;
  color: #e6a23c !important;
  border-color: #faecd8 !important;
}

.risk-low {
  background: #f0f9eb !important;
  color: #67c23a !important;
  border-color: #e1f3d8 !important;
}

/* 折叠面板 */
.report-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: #1d2129;
}

.stage-content {
  font-size: 13px;
  color: #4e5969;
  line-height: 1.8;
}

.json-block {
  background: #f7f8fa;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  color: #1d2129;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fef0f0;
  color: #f56c6c;
  border-radius: 6px;
  font-size: 13px;
}

.alert-icon {
  font-size: 16px;
}

.cove-box {
  background: #f0f9ff;
  border-left: 3px solid #1e3a8a;
  padding: 12px 14px;
  border-radius: 0 6px 6px 0;
  font-size: 13px;
  color: #1d2129;
  line-height: 1.7;
  white-space: pre-wrap;
}

.raw-json {
  background: #1d2129;
  color: #a5d6ff;
  padding: 16px;
  border-radius: 8px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow-y: auto;
}
</style>
