<script setup lang="ts">
import { Cpu } from '@element-plus/icons-vue'
import type { ModelItem } from '@/types/api'

const props = defineProps<{
  models: ModelItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const providerTagType = (provider: string): any => {
  const map: Record<string, any> = {
    zhipu: 'primary',
    deepseek: 'success',
    qwen: 'warning',
    moonshot: 'danger',
    doubao: 'info',
    minimax: '',
    openai: '',
  }
  return map[provider] || 'info'
}

const providerLabel = (provider: string) => {
  const map: Record<string, string> = {
    zhipu: '智谱 AI',
    deepseek: 'DeepSeek',
    qwen: '通义千问',
    moonshot: '月之暗面',
    doubao: '字节豆包',
    minimax: 'MiniMax',
    openai: 'OpenAI',
  }
  return map[provider] || provider
}
</script>

<template>
  <el-card shadow="hover" class="admin-card">
    <template #header>
      <div class="card-header">
        <span>模型配置总览</span>
        <el-button type="primary" size="small" :loading="loading" @click="emit('refresh')">
          刷新
        </el-button>
      </div>
    </template>

    <el-table :data="props.models" border v-loading="loading" style="width: 100%">
      <el-table-column prop="name" label="模型名称" min-width="180">
        <template #default="{ row }">
          <div class="model-name-cell">
            <el-icon class="model-icon"><Cpu /></el-icon>
            <span class="model-name-text">{{ row.name }}</span>
            <el-tag v-if="row.recommended" type="danger" size="small" effect="dark" class="rec-tag">
              推荐
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="provider" label="提供商" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="providerTagType(row.provider)" size="small" effect="light">
            {{ providerLabel(row.provider) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="100" align="center" />
      <el-table-column prop="id" label="模型 ID" min-width="160">
        <template #default="{ row }">
          <code class="model-id">{{ row.id }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="240" />
    </el-table>

    <el-empty
      v-if="!loading && props.models.length === 0"
      description="暂无可用模型，请检查环境变量配置"
      :image-size="80"
    />

    <div v-if="!loading && props.models.length > 0" class="model-summary">
      <span class="summary-text">
        当前系统已配置 <strong>{{ props.models.length }}</strong> 个可用模型，其中推荐模型
        <el-tag type="danger" size="small" effect="dark">{{ props.models.filter(m => m.recommended).length }}</el-tag> 个。
      </span>
    </div>
  </el-card>
</template>

<style scoped>
.admin-card {
  border-radius: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}

.model-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-icon {
  color: #2563eb;
  font-size: 16px;
}

.model-name-text {
  font-weight: 600;
  color: #1e293b;
}

.rec-tag {
  margin-left: 2px;
}

.model-id {
  font-size: 12px;
  color: #475569;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, monospace;
}

.model-summary {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.summary-text {
  font-size: 13px;
  color: #475569;
}

.summary-text strong {
  color: #1e40af;
  font-weight: 700;
}
</style>
