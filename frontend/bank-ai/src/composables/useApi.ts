import { ref } from 'vue'
import { ElMessage } from 'element-plus'

interface UseApiOptions {
  successMessage?: string
  errorMessage?: string
  showError?: boolean
}

export function useApi<T, Args extends any[] = any[]>(
  apiFn: (...args: Args) => Promise<T>,
  options: UseApiOptions = {}
) {
  const data = ref<T | null>(null)
  const loading = ref(false)
  const error = ref<Error | null>(null)

  const execute = async (...args: Args): Promise<T | null> => {
    loading.value = true
    error.value = null
    try {
      const res = await apiFn(...args)
      data.value = res
      if (options.successMessage) {
        ElMessage.success(options.successMessage)
      }
      return res
    } catch (err: any) {
      error.value = err
      if (options.showError !== false) {
        const msg = options.errorMessage || err.message || '请求失败'
        ElMessage.error(msg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const reset = () => {
    data.value = null
    loading.value = false
    error.value = null
  }

  return { data, loading, error, execute, reset }
}
