<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Cpu, DocumentChecked, RefreshRight } from '@element-plus/icons-vue'
import { useModelStore } from '@/store'
import { useRuleStore } from '@/store/rule'
import ModelSelector from '@/components/ModelSelector.vue'

const visible = defineModel<boolean>('visible', { default: false })

const modelStore = useModelStore()
const ruleStore = useRuleStore()

const activeTab = ref('model')

const clauseOptions = [
  '违约责任',
  '保密条款',
  '知识产权',
  '争议解决',
]

onMounted(() => {
  ruleStore.init()
  if (modelStore.models.length === 0) {
    modelStore.fetchModels()
  }
})
</script>

<template>
  <el-dialog
    v-model="visible"
    title="系统设置"
    width="560px"
    :close-on-click-modal="false"
    class="settings-dialog"
  >
    <el-tabs v-model="activeTab" class="settings-tabs">
      <!-- 模型设置 -->
      <el-tab-pane name="model">
        <template #label>
          <span class="tab-label">
            <el-icon><Cpu /></el-icon>
            <span>模型设置</span>
          </span>
        </template>
        <div class="settings-section">
          <div class="section-title">默认 AI 模型</div>
          <div class="section-desc">选择用于合同比对和智能对话的默认大模型</div>
          <ModelSelector v-model="modelStore.currentModelId" class="model-setting-row" />
        </div>
      </el-tab-pane>

      <!-- 合规规则设置 -->
      <el-tab-pane name="rules">
        <template #label>
          <span class="tab-label">
            <el-icon><DocumentChecked /></el-icon>
            <span>合规规则</span>
          </span>
        </template>
        <div class="settings-section">
          <el-form label-position="top" class="rule-form">
            <!-- 金额容差比例 -->
            <el-form-item label="金额容差比例">
              <div class="tolerance-row">
                <el-input-number
                  v-model="ruleStore.priceTolerance"
                  :min="0"
                  :max="100"
                  :precision="2"
                  :step="0.5"
                  controls-position="right"
                  class="tolerance-input"
                />
                <span class="tolerance-unit">%</span>
              </div>
              <div class="form-hint">
                金额差异在此百分比范围内视为"一致"，不计入风险差异
              </div>
            </el-form-item>

            <!-- 必检条款清单 -->
            <el-form-item label="必检条款清单">
              <el-select
                v-model="ruleStore.requiredClauses"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="请选择或输入必检条款"
                class="clause-select"
              >
                <el-option
                  v-for="item in clauseOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
              <div class="form-hint">
                缺失的条款将在比对结果中标记为高风险缺失项
              </div>
            </el-form-item>

            <!-- 自定义审查要求 -->
            <el-form-item label="自定义审查要求">
              <el-input
                v-model="ruleStore.customRequirements"
                type="textarea"
                :rows="3"
                placeholder="例如：请重点关注交付周期是否超过30天，输出风险时请按照【风险等级-原因-修改建议】的格式"
                resize="none"
              />
              <div class="form-hint">
                大模型将以最高优先级遵循此要求调整分析和输出格式
              </div>
            </el-form-item>
          </el-form>

          <div class="reset-row">
            <el-button type="info" text :icon="RefreshRight" @click="ruleStore.resetRules">
              恢复默认规则
            </el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button type="primary" @click="visible = false">完成</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.settings-dialog :deep(.el-dialog__header) {
  margin: 0;
  padding: 20px 24px 16px;
  border-bottom: 1px solid #f0f2f5;
}

.settings-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}

.settings-dialog :deep(.el-dialog__footer) {
  padding: 12px 24px 20px;
  border-top: 1px solid #f0f2f5;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.settings-section {
  padding: 8px 4px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: #86909c;
  margin-bottom: 16px;
}

.model-setting-row {
  margin-top: 8px;
}

.rule-form :deep(.el-form-item__label) {
  font-size: 14px;
  font-weight: 500;
  color: #1d2129;
  padding-bottom: 6px;
}

.tolerance-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tolerance-input {
  width: 140px;
}

.tolerance-unit {
  font-size: 14px;
  color: #4e5969;
  font-weight: 500;
}

.clause-select {
  width: 100%;
}

.form-hint {
  font-size: 12px;
  color: #86909c;
  margin-top: 6px;
  line-height: 1.5;
}

.reset-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
