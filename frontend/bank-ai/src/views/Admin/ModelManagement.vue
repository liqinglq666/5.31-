<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Check, Delete, Edit } from '@element-plus/icons-vue'
import {
  getModelConfigs,
  createModelConfig,
  updateModelConfig,
  deleteModelConfig,
  setActiveModel,
} from '@/api/admin'
import type { ModelConfigItem } from '@/types/api'

const tableData = ref<ModelConfigItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)

const form = ref({
  provider: 'openai',
  model_name: '',
  api_model_id: '',
  base_url: '',
  api_key: '',
  temperature: 0.0,
  is_active: false,
})

const providers = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '阿里通义千问', value: 'qwen' },
  { label: '智谱 AI', value: 'zhipu' },
  { label: 'Moonshot', value: 'moonshot' },
  { label: '字节豆包', value: 'doubao' },
  { label: 'MiniMax', value: 'minimax' },
]

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getModelConfigs()
    if (res.data.code === 200) {
      tableData.value = res.data.data
    }
  } catch (_err) {
    ElMessage.error('获取模型配置失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  isEdit.value = false
  editId.value = null
  form.value = {
    provider: 'openai',
    model_name: '',
    api_model_id: '',
    base_url: '',
    api_key: '',
    temperature: 0.0,
    is_active: false,
  }
  dialogVisible.value = true
}

const openEdit = (row: ModelConfigItem) => {
  isEdit.value = true
  editId.value = row.id
  form.value = {
    provider: row.provider,
    model_name: row.model_name,
    api_model_id: row.api_model_id || '',
    base_url: row.base_url || '',
    api_key: '',
    temperature: parseFloat(row.temperature || '0.0'),
    is_active: row.is_active,
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!form.value.model_name.trim()) {
    ElMessage.warning('模型名称不能为空')
    return
  }
  if (!isEdit.value && !form.value.api_key.trim()) {
    ElMessage.warning('API Key 不能为空')
    return
  }

  try {
    if (isEdit.value && editId.value !== null) {
      const payload: any = {
        provider: form.value.provider,
        model_name: form.value.model_name,
        api_model_id: form.value.api_model_id || undefined,
        base_url: form.value.base_url || undefined,
        temperature: String(form.value.temperature ?? 0.0),
        is_active: form.value.is_active,
      }
      if (form.value.api_key.trim()) {
        payload.api_key = form.value.api_key
      }
      await updateModelConfig(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createModelConfig({
        provider: form.value.provider,
        model_name: form.value.model_name.trim(),
        api_model_id: form.value.api_model_id || undefined,
        base_url: form.value.base_url || undefined,
        api_key: form.value.api_key.trim(),
        temperature: String(form.value.temperature ?? 0.0),
        is_active: form.value.is_active,
      })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } catch (_err) {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  }
}

const handleDelete = async (row: ModelConfigItem) => {
  try {
    await ElMessageBox.confirm(`确认删除模型配置 ${row.model_name}？`, '提示', {
      type: 'warning',
    })
    await deleteModelConfig(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (_err: any) {
    if (_err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleSetActive = async (row: ModelConfigItem) => {
  try {
    await setActiveModel(row.id)
    ElMessage.success(`已切换至 ${row.model_name}`)
    fetchData()
  } catch (_err) {
    ElMessage.error('切换失败')
  }
}

onMounted(fetchData)
</script>

<template>
  <div class="model-management">
    <div class="page-header">
      <h2 class="page-title">模型管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">
        新增模型配置
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>
        <span>
          本系统底层采用 OpenAI 协议。非 OpenAI 体系模型（如 Claude）请填写兼容代理层（如 OneAPI / LiteLLM）的 BaseURL。
        </span>
      </template>
    </el-alert>

    <el-table :data="tableData" v-loading="loading" border stripe>
      <el-table-column prop="provider" label="服务商" width="120" />
      <el-table-column prop="model_name" label="模型名称" min-width="140" />
      <el-table-column prop="api_model_id" label="API模型ID" min-width="140" />
      <el-table-column prop="base_url" label="BaseURL" min-width="200" show-overflow-tooltip />
      <el-table-column prop="api_key" label="API Key" width="160">
        <template #default="{ row }">
          <span class="masked-key">{{ row.api_key }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="temperature" label="温度" width="80" align="center" />
      <el-table-column prop="is_active" label="当前激活" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_active" type="success" size="small">激活</el-tag>
          <span v-else class="inactive-text">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.is_active"
            type="primary"
            link
            size="small"
            :icon="Check"
            @click="handleSetActive(row)"
          >
            设为当前
          </el-button>
          <el-button type="primary" link size="small" :icon="Edit" @click="openEdit(row)">
            编辑
          </el-button>
          <el-button type="danger" link size="small" :icon="Delete" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑模型配置' : '新增模型配置'"
      width="520px"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="服务商">
          <el-select v-model="form.provider" placeholder="请选择服务商" style="width: 100%">
            <el-option
              v-for="p in providers"
              :key="p.value"
              :label="p.label"
              :value="p.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" placeholder="前端显示名称，如 DeepSeek V3" />
        </el-form-item>
        <el-form-item label="API模型ID">
          <el-input v-model="form.api_model_id" placeholder="实际API模型ID，如 deepseek-chat" />
        </el-form-item>
        <el-form-item label="BaseURL">
          <el-input
            v-model="form.base_url"
            placeholder="可选，如 https://api.openai.com/v1"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="isEdit ? '留空表示不修改' : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number
            v-model="form.temperature"
            :min="0"
            :max="2"
            :step="0.1"
            :precision="1"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="设为当前">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-management {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1d2129;
  margin: 0;
}

.masked-key {
  font-family: monospace;
  color: #606266;
  font-size: 13px;
}

.inactive-text {
  color: #c0c4cc;
}
</style>
