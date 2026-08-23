import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'smartpact_compare_rules'

export interface CompareRules {
  priceTolerance: number
  requiredClauses: string[]
  customRequirements: string
}

function loadRules(): CompareRules {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        priceTolerance: Number(parsed.priceTolerance) || 0,
        requiredClauses: Array.isArray(parsed.requiredClauses)
          ? parsed.requiredClauses
          : ['违约责任', '保密条款'],
        customRequirements: String(parsed.customRequirements || ''),
      }
    }
  } catch {
    // ignore
  }
  return {
    priceTolerance: 0,
    requiredClauses: ['违约责任', '保密条款'],
    customRequirements: '',
  }
}

function saveRules(rules: CompareRules) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rules))
}

export const useRuleStore = defineStore('rule', () => {
  const priceTolerance = ref<number>(0)
  const requiredClauses = ref<string[]>(['违约责任', '保密条款'])
  const customRequirements = ref<string>('')

  // 初始化从 localStorage 加载
  const init = () => {
    const saved = loadRules()
    priceTolerance.value = saved.priceTolerance
    requiredClauses.value = saved.requiredClauses
    customRequirements.value = saved.customRequirements
  }

  // 持久化监听
  watch(
    [priceTolerance, requiredClauses, customRequirements],
    () => {
      saveRules({
        priceTolerance: priceTolerance.value,
        requiredClauses: requiredClauses.value,
        customRequirements: customRequirements.value,
      })
    },
    { deep: true }
  )

  const resetRules = () => {
    priceTolerance.value = 0
    requiredClauses.value = ['违约责任', '保密条款']
    customRequirements.value = ''
  }

  return {
    priceTolerance,
    requiredClauses,
    customRequirements,
    init,
    resetRules,
  }
})
