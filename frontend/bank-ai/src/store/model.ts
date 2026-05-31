import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { getAvailableModels } from '@/api'
import type { ModelItem } from '@/types/api'

export interface ModelGroup {
  provider: string
  models: ModelItem[]
}

const CURRENT_MODEL_KEY = 'smartpact_current_model_id'

export const useModelStore = defineStore('model', () => {
  const models = ref<ModelItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 当前选中的模型 ID（优先从 localStorage 恢复）
  const currentModelId = ref<string>('')

  const groupedModels = computed<ModelGroup[]>(() => {
    const map = new Map<string, ModelItem[]>()
    for (const m of models.value) {
      if (!map.has(m.provider)) {
        map.set(m.provider, [])
      }
      map.get(m.provider)!.push(m)
    }
    return Array.from(map.entries()).map(([provider, models]) => ({
      provider,
      models,
    }))
  })

  const recommendedModel = computed(() =>
    models.value.find((m) => m.recommended) || models.value[0] || null
  )

  // 当前生效模型：用户手动选择的 > 后端推荐的 > 第一个可用
  const currentModel = computed(() => {
    if (currentModelId.value) {
      const found = models.value.find((m) => m.id === currentModelId.value)
      if (found) return found
    }
    return recommendedModel.value
  })

  // 持久化 currentModelId
  watch(currentModelId, (val) => {
    if (val) {
      localStorage.setItem(CURRENT_MODEL_KEY, val)
    } else {
      localStorage.removeItem(CURRENT_MODEL_KEY)
    }
  })

  const fetchModels = async () => {
    loading.value = true
    error.value = null
    try {
      const res = await getAvailableModels()
      models.value = res.data.data || []
      // 加载完成后，如果 localStorage 有保存的模型 ID 且有效，则恢复
      const savedId = localStorage.getItem(CURRENT_MODEL_KEY)
      if (savedId && models.value.some((m) => m.id === savedId)) {
        currentModelId.value = savedId
      }
    } catch (err: any) {
      error.value = err.message || '获取模型列表失败'
    } finally {
      loading.value = false
    }
  }

  const setCurrentModel = (id: string) => {
    currentModelId.value = id
  }

  return {
    models,
    loading,
    error,
    currentModelId,
    groupedModels,
    recommendedModel,
    currentModel,
    fetchModels,
    setCurrentModel,
  }
})
