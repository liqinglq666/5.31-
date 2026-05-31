<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document, View, Delete, MagicStick } from '@element-plus/icons-vue'
import FilePreviewDialog from '@/components/FilePreviewDialog.vue'
import { useModelStore } from '@/store'
import { useRuleStore } from '@/store/rule'
import { postMatchFiles } from '@/api'
import type { MatchPair } from '@/api'

const props = defineProps<{
  compact?: boolean
}>()

const isComparing = defineModel<boolean>('loading', { default: false })

const emit = defineEmits<{
  (e: 'start', formData: FormData): void
  (e: 'start-batch', formDataList: FormData[], concurrency: number): void
}>()

const modelStore = useModelStore()
const ruleStore = useRuleStore()

// ---------------------------------------------------------------------------
// 文件队列（批量模式）
// ---------------------------------------------------------------------------
const sourceFiles = ref<File[]>([])
const contractFiles = ref<File[]>([])

const pairCount = computed(() =>
  Math.min(sourceFiles.value.length, contractFiles.value.length)
)

const onProcurementChange = (uploadFile: any) => {
  if (uploadFile.raw) {
    sourceFiles.value.push(uploadFile.raw)
  }
}

const onContractChange = (uploadFile: any) => {
  if (uploadFile.raw) {
    contractFiles.value.push(uploadFile.raw)
  }
}

const removeFile = (index: number, type: 'source' | 'contract') => {
  if (type === 'source') {
    sourceFiles.value.splice(index, 1)
  } else {
    contractFiles.value.splice(index, 1)
  }
}

const clearSourceFiles = () => {
  sourceFiles.value = []
}

const clearContractFiles = () => {
  contractFiles.value = []
}

// ---------------------------------------------------------------------------
// 智能配对
// ---------------------------------------------------------------------------
const isMatching = ref(false)
const matchedPairs = ref<MatchPair[]>([])
const unmatchedSourceIndices = ref<number[]>([])
const unmatchedContractIndices = ref<number[]>([])

const handleSmartMatch = async () => {
  if (sourceFiles.value.length === 0 || contractFiles.value.length === 0) {
    ElMessage.warning('请先在两侧上传文件后再进行智能配对')
    return
  }
  isMatching.value = true
  try {
    const res = await postMatchFiles({
      source_names: sourceFiles.value.map((f) => f.name),
      contract_names: contractFiles.value.map((f) => f.name),
    })
    const data = res.data.data
    matchedPairs.value = data.pairs || []
    unmatchedSourceIndices.value = data.unmatched_source || []
    unmatchedContractIndices.value = data.unmatched_contract || []

    // 将已配对文件按索引对齐到数组前部
    if (matchedPairs.value.length > 0) {
      const newSourceFiles: File[] = []
      const newContractFiles: File[] = []
      const usedSource = new Set<number>()
      const usedContract = new Set<number>()

      for (const pair of matchedPairs.value) {
        const sf = sourceFiles.value[pair.source_index]
        const cf = contractFiles.value[pair.contract_index]
        if (!sf || !cf) continue
        newSourceFiles.push(sf)
        newContractFiles.push(cf)
        usedSource.add(pair.source_index)
        usedContract.add(pair.contract_index)
      }

      for (let i = 0; i < sourceFiles.value.length; i++) {
        const f = sourceFiles.value[i]
        if (!f) continue
        if (!usedSource.has(i)) newSourceFiles.push(f)
      }
      for (let i = 0; i < contractFiles.value.length; i++) {
        const f = contractFiles.value[i]
        if (!f) continue
        if (!usedContract.has(i)) newContractFiles.push(f)
      }

      sourceFiles.value = newSourceFiles
      contractFiles.value = newContractFiles

      // 索引已变更，清空配对索引引用，避免 UI 错位
      matchedPairs.value = []
    }

    const totalPairs = Math.min(sourceFiles.value.length, contractFiles.value.length)
    ElMessage.success(`智能配对完成，共匹配 ${totalPairs} 对文件`)
  } catch (_err) {
    ElMessage.error('智能配对失败，请稍后重试')
  } finally {
    isMatching.value = false
  }
}

// ---------------------------------------------------------------------------
// 并发控制
// ---------------------------------------------------------------------------
const concurrency = ref(3)

// ---------------------------------------------------------------------------
// 批量进度
// ---------------------------------------------------------------------------
const isBatching = ref(false)
const batchCurrent = ref(0)
const batchTotal = ref(0)

const batchPercentage = computed(() => {
  if (batchTotal.value === 0) return 0
  return Math.round((batchCurrent.value / batchTotal.value) * 100)
})

const batchFormat = computed(() => {
  return () => `${batchCurrent.value}/${batchTotal.value} 已完成`
})

defineExpose({
  updateBatchProgress: (current: number, total: number) => {
    batchCurrent.value = current
    batchTotal.value = total
    if (current >= total) {
      isBatching.value = false
    }
  },
})

// ---------------------------------------------------------------------------
// FormData 构造
// ---------------------------------------------------------------------------
const buildFormData = (procurement: File, contract: File): FormData => {
  const formData = new FormData()
  formData.append('procurement', procurement)
  formData.append('contract', contract)
  if (modelStore.currentModelId) {
    formData.append('model_id', modelStore.currentModelId)
  }
  if (ruleStore.priceTolerance > 0) {
    formData.append('price_tolerance', String(ruleStore.priceTolerance))
  }
  if (ruleStore.requiredClauses.length > 0) {
    ruleStore.requiredClauses.forEach((clause) => {
      formData.append('required_clauses', clause)
    })
  }
  if (ruleStore.customRequirements.trim()) {
    formData.append('custom_requirements', ruleStore.customRequirements.trim())
  }
  return formData
}

// ---------------------------------------------------------------------------
// 开始比对
// ---------------------------------------------------------------------------
const handleStart = () => {
  const count = pairCount.value
  if (count === 0) return

  if (count === 1) {
    isBatching.value = false
    const p = sourceFiles.value[0]
    const c = contractFiles.value[0]
    if (!p || !c) return
    const formData = buildFormData(p, c)
    emit('start', formData)
    return
  }

  // 批量模式
  isBatching.value = true
  batchCurrent.value = 0
  batchTotal.value = count

  const formDataList: FormData[] = []
  for (let i = 0; i < count; i++) {
    const p = sourceFiles.value[i]
    const c = contractFiles.value[i]
    if (!p || !c) continue
    formDataList.push(buildFormData(p, c))
  }
  emit('start-batch', formDataList, concurrency.value)
}

// ---------------------------------------------------------------------------
// 在线预览
// ---------------------------------------------------------------------------
const previewVisible = ref(false)
const previewFile = ref<File | null>(null)

const handlePreview = (file: File | null) => {
  if (!file) return
  previewFile.value = file
  previewVisible.value = true
}
</script>

<template>
  <el-card shadow="hover" class="upload-card" :class="{ 'upload-card--compact': compact }">
    <template #header>
      <div class="card-header">
        <el-icon><UploadFilled /></el-icon>
        <span>{{ compact ? '文件来源' : '文件上传' }}</span>
      </div>
    </template>

    <!-- 完整上传模式 -->
    <template v-if="!compact">
      <div class="upload-section">
        <div class="upload-label">采购结果文件</div>
        <el-upload
          drag
          :auto-upload="false"
          :show-file-list="false"
          :multiple="true"
          accept=".txt,.pdf,.doc,.docx"
          @change="onProcurementChange"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 txt / pdf / word 格式，可一次添加多个</div>
          </template>
        </el-upload>

        <!-- 采购文件队列 -->
        <div v-if="sourceFiles.length > 0" class="file-queue">
          <div class="queue-header">
            <span>已添加文件 ({{ sourceFiles.length }})</span>
            <el-button type="danger" size="small" text :icon="Delete" @click="clearSourceFiles">
              清空
            </el-button>
          </div>
          <div
            v-for="(file, index) in sourceFiles"
            :key="`src-${index}`"
            class="queue-item"
          >
            <el-icon class="queue-icon"><Document /></el-icon>
            <span class="queue-name" :title="file.name">{{ file.name }}</span>
            <div class="queue-actions">
              <el-button
                type="primary"
                size="small"
                text
                :icon="View"
                @click="handlePreview(file)"
              />
              <el-button
                type="danger"
                size="small"
                text
                :icon="Delete"
                @click="removeFile(index, 'source')"
              />
            </div>
          </div>
        </div>
      </div>

      <el-divider content-position="center">
        <el-button
          type="warning"
          size="small"
          :loading="isMatching"
          :disabled="sourceFiles.length === 0 || contractFiles.length === 0"
          @click="handleSmartMatch"
        >
          <el-icon><MagicStick /></el-icon>
          {{ isMatching ? '配对中...' : '智能配对' }}
        </el-button>
      </el-divider>

      <div class="upload-section">
        <div class="upload-label">最终合同文件</div>
        <el-upload
          drag
          :auto-upload="false"
          :show-file-list="false"
          :multiple="true"
          accept=".txt,.pdf,.doc,.docx"
          @change="onContractChange"
        >
          <el-icon class="el-icon--upload"><Document /></el-icon>
          <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 txt / pdf / word 格式，可一次添加多个</div>
          </template>
        </el-upload>

        <!-- 合同文件队列 -->
        <div v-if="contractFiles.length > 0" class="file-queue">
          <div class="queue-header">
            <span>已添加文件 ({{ contractFiles.length }})</span>
            <el-button type="danger" size="small" text :icon="Delete" @click="clearContractFiles">
              清空
            </el-button>
          </div>
          <div
            v-for="(file, index) in contractFiles"
            :key="`ctr-${index}`"
            class="queue-item"
          >
            <el-icon class="queue-icon"><Document /></el-icon>
            <span class="queue-name" :title="file.name">{{ file.name }}</span>
            <div class="queue-actions">
              <el-button
                type="primary"
                size="small"
                text
                :icon="View"
                @click="handlePreview(file)"
              />
              <el-button
                type="danger"
                size="small"
                text
                :icon="Delete"
                @click="removeFile(index, 'contract')"
              />
            </div>
          </div>
        </div>
      </div>

    </template>

    <!-- 紧凑模式 -->
    <template v-else>
      <div class="compact-section">
        <div class="compact-item">
          <div class="compact-label">
            采购结果 {{ sourceFiles.length > 1 ? `(${sourceFiles.length})` : '' }}
          </div>
          <div class="compact-row">
            <el-icon class="compact-icon"><Document /></el-icon>
            <span class="compact-name" :title="sourceFiles[0]?.name"
              >{{ sourceFiles[0]?.name || '未选择' }}</span
            >
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".txt,.pdf,.doc,.docx"
              @change="onProcurementChange"
            >
              <el-button type="primary" size="small" text> 添加 </el-button>
            </el-upload>
            <el-button
              v-if="sourceFiles.length > 0"
              type="danger"
              size="small"
              text
              :icon="Delete"
              @click="clearSourceFiles"
            />
            <el-button
              v-if="sourceFiles.length > 0"
              type="primary"
              size="small"
              :icon="View"
              text
              @click="handlePreview(sourceFiles[0] || null)"
            />
          </div>
        </div>

        <el-divider class="compact-divider" />

        <div class="compact-item">
          <div class="compact-label">
            最终合同 {{ contractFiles.length > 1 ? `(${contractFiles.length})` : '' }}
          </div>
          <div class="compact-row">
            <el-icon class="compact-icon"><Document /></el-icon>
            <span class="compact-name" :title="contractFiles[0]?.name"
              >{{ contractFiles[0]?.name || '未选择' }}</span
            >
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".txt,.pdf,.doc,.docx"
              @change="onContractChange"
            >
              <el-button type="primary" size="small" text> 添加 </el-button>
            </el-upload>
            <el-button
              v-if="contractFiles.length > 0"
              type="danger"
              size="small"
              text
              :icon="Delete"
              @click="clearContractFiles"
            />
            <el-button
              v-if="contractFiles.length > 0"
              type="primary"
              size="small"
              :icon="View"
              text
              @click="handlePreview(contractFiles[0] || null)"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- 批量进度条 -->
    <div v-if="isBatching" class="batch-progress">
      <el-progress
        :percentage="batchPercentage"
        :format="batchFormat"
        :stroke-width="16"
        status="success"
      />
    </div>

    <div class="compare-row">
      <el-select
        v-if="pairCount > 1"
        v-model="concurrency"
        size="large"
        class="concurrency-select"
        title="同时提交任务数，数值越小越稳定"
      >
        <el-option
          v-for="n in 5"
          :key="n"
          :label="`并发 ${n}`"
          :value="n"
        />
      </el-select>
      <el-button
        type="primary"
        size="large"
        class="compare-btn"
        :class="{ 'compare-btn--compact': compact }"
        :loading="isComparing"
        :disabled="pairCount === 0"
        @click="handleStart"
      >
        {{ pairCount <= 1 ? '开始智能比对' : `开始批量比对 (${pairCount} 对)` }}
      </el-button>
    </div>

    <!-- 文件预览弹窗 -->
    <FilePreviewDialog v-model:visible="previewVisible" :file="previewFile" />
  </el-card>
</template>

<style scoped>
.upload-card {
  border-radius: 12px;
  min-height: 560px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}

.upload-section {
  margin-bottom: 8px;
}

.upload-label {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  margin-bottom: 8px;
}

/* ---------------------------------------------------------------------------
   文件队列
   --------------------------------------------------------------------------- */
.file-queue {
  margin-top: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
}

.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed #e2e8f0;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: background 0.2s ease;
}

.queue-item:hover {
  background: #f1f5f9;
}

.queue-icon {
  color: #0284c7;
  font-size: 16px;
  flex-shrink: 0;
}

.queue-name {
  flex: 1;
  font-size: 13px;
  color: #0c4a6e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* ---------------------------------------------------------------------------
   配对摘要
   --------------------------------------------------------------------------- */
/* ---------------------------------------------------------------------------
   批量进度
   --------------------------------------------------------------------------- */
.batch-progress {
  margin: 16px 0 8px;
}

.compare-row {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.concurrency-select {
  width: 110px;
  flex-shrink: 0;
}

.compare-btn {
  flex: 1;
  font-size: 16px;
  letter-spacing: 2px;
  background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%);
  border: none;
}

.compare-btn:hover {
  background: linear-gradient(90deg, #1d4ed8 0%, #1e40af 100%);
}

.compare-btn--compact {
  margin-top: 12px;
  font-size: 14px;
  letter-spacing: 1px;
}

/* ---------------------------------------------------------------------------
   紧凑模式样式
   --------------------------------------------------------------------------- */
.upload-card--compact {
  min-height: auto;
}

.compact-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.compact-item {
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
}

.compact-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}

.compact-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.compact-icon {
  color: #0284c7;
  font-size: 16px;
}

.compact-name {
  flex: 1;
  font-size: 13px;
  color: #0c4a6e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-divider {
  margin: 4px 0;
}

.compact-row :deep(.el-upload) {
  display: inline-block;
}
</style>
