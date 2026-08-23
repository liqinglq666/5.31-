import { ref, onUnmounted } from 'vue'

export interface UsePollingOptions<T> {
  interval?: number
  maxAttempts?: number
  onResult?: (result: T) => boolean | void
  onError?: (err: Error) => void
}

export function usePolling<T>(
  pollFn: () => Promise<T>,
  options: UsePollingOptions<T> = {}
) {
  const data = ref<T | null>(null)
  const isPolling = ref(false)
  const attempts = ref(0)
  let timer: number | null = null

  const stop = () => {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    isPolling.value = false
    attempts.value = 0
  }

  const start = async () => {
    if (isPolling.value) return
    isPolling.value = true
    attempts.value = 0

    const tick = async () => {
      if (options.maxAttempts && attempts.value >= options.maxAttempts) {
        stop()
        return
      }
      attempts.value++

      try {
        const res = await pollFn()
        data.value = res
        const shouldStop = options.onResult?.(res)
        if (shouldStop === true) {
          stop()
        }
      } catch (err: any) {
        options.onError?.(err)
        stop()
      }
    }

    await tick()
    timer = window.setInterval(tick, options.interval || 1500)
  }

  onUnmounted(stop)

  return { data, isPolling, attempts, start, stop }
}
