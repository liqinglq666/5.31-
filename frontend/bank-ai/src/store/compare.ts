import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { postCompare, getStatus, cancelCompare, getRunningTasks } from '@/api/compare'
import { getRecords } from '@/api/task'
import type { TaskResult, RunningTask } from '@/types/api'

export const useCompareStore = defineStore('compare', () => {
  // ---------------------------------------------------------------------------
  // 多任务队列状态
  // ---------------------------------------------------------------------------
  const activeTasks = ref<RunningTask[]>([])
  const recentTasks = ref<RunningTask[]>([])
  const currentViewTaskId = ref('')

  // 用于重试的 FormData 缓存（仅当前会话有效，刷新后丢失）
  const taskFormDataMap = new Map<string, FormData>()

  // V3.1 视觉溯源：合同文件 Blob URL 缓存（taskId → blobUrl）
  const contractBlobUrlMap = new Map<string, string>()

  const getContractBlobUrl = (taskId: string): string | undefined =>
    contractBlobUrlMap.get(taskId)

  // ---------------------------------------------------------------------------
  // 兼容旧接口的状态（从 currentViewTaskId 对应的任务派生）
  // ---------------------------------------------------------------------------
  const taskResult = ref<TaskResult | null>(null)
  const currentTaskId = ref('')
  const currentCreatorName = ref('')
  const currentCreatorEmpId = ref('')

  const isComparing = computed(() => activeTasks.value.length > 0)

  const hasReport = computed(() => !!taskResult.value)

  const progressVisible = computed(() => {
    const task = activeTasks.value.find((t) => t.taskId === currentViewTaskId.value)
    return !!task && task.visible
  })

  const progressPercent = computed(() => {
    const task = activeTasks.value.find((t) => t.taskId === currentViewTaskId.value)
    return task ? task.progress : 0
  })

  const progressStatus = computed(() => {
    const task = activeTasks.value.find((t) => t.taskId === currentViewTaskId.value)
    return task ? task.message : ''
  })

  const progressProcessMode = computed(() => {
    const task = activeTasks.value.find((t) => t.taskId === currentViewTaskId.value)
    return task ? task.processMode || '' : ''
  })

  const isCancelling = computed(() => {
    const task = activeTasks.value.find((t) => t.taskId === currentViewTaskId.value)
    return task ? !!task.isCancelling : false
  })

  // ---------------------------------------------------------------------------
  // 辅助函数
  // ---------------------------------------------------------------------------
  const getTaskById = (taskId: string) => activeTasks.value.find((t) => t.taskId === taskId)

  const showTaskProgress = (taskId: string) => {
    currentViewTaskId.value = taskId
    const task = getTaskById(taskId)
    if (task) {
      task.visible = true
    }
  }

  const hideTaskProgress = (taskId: string) => {
    const task = getTaskById(taskId)
    if (task) {
      task.visible = false
    }
    if (currentViewTaskId.value === taskId) {
      currentViewTaskId.value = ''
    }
  }

  const clearTaskInterval = (task: RunningTask) => {
    if (task.intervalId) {
      clearInterval(task.intervalId)
      task.intervalId = undefined
    }
  }

  // ---------------------------------------------------------------------------
  // 桌面通知
  // ---------------------------------------------------------------------------
  const sendNotification = (title: string, body: string) => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      new Notification(title, { body, icon: '/logo.png' })
    }
  }

  // ---------------------------------------------------------------------------
  // 独立轮询
  // ---------------------------------------------------------------------------
  const startPolling = (taskId: string) => {
    const task = getTaskById(taskId)
    if (!task) return

    _doPoll(taskId)

    const intervalId = window.setInterval(() => {
      _doPoll(taskId)
    }, 1500)

    task.intervalId = intervalId
  }

  const _doPoll = async (taskId: string) => {
    const task = getTaskById(taskId)
    if (!task) return

    try {
      const statusRes = await getStatus(taskId)
      const { status, progress, message, result, process_mode } = statusRes.data.data

      task.progress = progress || 0
      task.message = message || '处理中...'
      if (process_mode) {
        task.processMode = process_mode
      }

      if (status === 'completed') {
        clearTaskInterval(task)
        task.status = 'completed'
        task.result = result
        task.progress = 100
        moveToRecent(taskId)
        sendNotification('智契 SMARTPACT', `比对任务已完成：${task.fileName}`)
      } else if (status === 'failed') {
        clearTaskInterval(task)
        task.status = 'failed'
        task.message = message || '任务执行失败'
        moveToRecent(taskId)
        ElMessage.error(`任务失败: ${task.fileName}`)
      } else if (status === 'cancelled') {
        clearTaskInterval(task)
        task.status = 'cancelled'
        moveToRecent(taskId)
        ElMessage.info('任务已取消')
      }
    } catch (_err) {
      clearTaskInterval(task)
      task.status = 'failed'
      task.message = '轮询任务状态时发生网络错误'
      moveToRecent(taskId)
    }
  }

  const moveToRecent = (taskId: string) => {
    const idx = activeTasks.value.findIndex((t) => t.taskId === taskId)
    if (idx === -1) return
    const task = activeTasks.value[idx]!
    activeTasks.value.splice(idx, 1)

    if (currentViewTaskId.value === taskId) {
      currentViewTaskId.value = ''
    }

    taskFormDataMap.delete(taskId)

    recentTasks.value.unshift(task)
    if (recentTasks.value.length > 20) {
      recentTasks.value.pop()
    }
  }

  // ---------------------------------------------------------------------------
  // 启动单个任务
  // ---------------------------------------------------------------------------
  const startTask = async (
    formData: FormData,
    options?: {
      batchInfo?: { current: number; total: number }
      visible?: boolean
    }
  ): Promise<string> => {
    const visible = options?.visible !== false
    const batchInfo = options?.batchInfo

    const res = await postCompare(formData)
    const { task_id } = res.data.data

    const fileA = formData.get('procurement') as File | null
    const fileB = formData.get('contract') as File | null
    const fileName = `${fileA?.name || '采购结果'} vs ${fileB?.name || '合同'}`

    const task: RunningTask = {
      taskId: task_id,
      fileName,
      status: 'pending',
      progress: 0,
      message: batchInfo
        ? `[${batchInfo.current}/${batchInfo.total}] 任务已创建，正在等待处理...`
        : '任务已创建，正在等待处理...',
      startTime: new Date().toISOString(),
      visible,
      batchInfo,
    }

    activeTasks.value.push(task)
    taskFormDataMap.set(task_id, formData)

    // V3.1 保存合同文件 blob URL，供视觉溯源使用
    const contractFile = formData.get('contract') as File | null
    if (contractFile) {
      contractBlobUrlMap.set(task_id, URL.createObjectURL(contractFile))
    }

    if (visible) {
      currentViewTaskId.value = task_id
    }

    startPolling(task_id)
    return task_id
  }

  // ---------------------------------------------------------------------------
  // 批量比对（支持前端并发控制，按指定并发数分批提交）
  // ---------------------------------------------------------------------------
  const runBatchCompare = async (
    formDataList: FormData[],
    onProgress?: (current: number, total: number) => void,
    concurrency = 5
  ): Promise<string[]> => {
    if (formDataList.length === 0) return []

    const taskIds: string[] = []
    let completedCount = 0
    let index = 0

    const waitForTask = (taskId: string): Promise<void> => {
      return new Promise((resolve) => {
        const check = () => {
          const stillActive = activeTasks.value.some((t) => t.taskId === taskId)
          if (!stillActive) {
            resolve()
          } else {
            setTimeout(check, 1000)
          }
        }
        check()
      })
    }

    const runOne = async (): Promise<void> => {
      if (index >= formDataList.length) return
      const i = index++
      const fd = formDataList[i]!
      let taskId: string | null = null
      try {
        taskId = await startTask(fd, {
          batchInfo: { current: i + 1, total: formDataList.length },
          visible: i === 0,
        })
        if (taskId) taskIds.push(taskId)
      } catch (_err) {
        ElMessage.error(`第 ${i + 1} 个任务提交失败`)
        return
      }

      // 等待该任务完成（从 activeTasks 移除）后再释放槽位，
      // 这样 concurrency=1 时后端真正只处理 1 个任务。
      if (taskId) {
        await waitForTask(taskId)
        completedCount++
        if (onProgress) onProgress(completedCount, formDataList.length)
      }
    }

    // 使用 Promise 池控制并发数
    const pool: Promise<void>[] = []
    const enqueue = () => {
      if (index >= formDataList.length) return
      const p = runOne().finally(() => {
        enqueue() // 当前槽位释放，启动下一个
      })
      pool.push(p)
    }

    // 初始启动 concurrency 个任务
    for (let i = 0; i < Math.min(concurrency, formDataList.length); i++) {
      enqueue()
    }

    await Promise.all(pool)
    return taskIds
  }

  // ---------------------------------------------------------------------------
  // 取消任务
  // ---------------------------------------------------------------------------
  const cancelTask = async (taskId: string) => {
    const task = getTaskById(taskId)
    if (!task) return
    task.isCancelling = true
    try {
      await cancelCompare(taskId)
      ElMessage.success('已发送取消请求')
    } catch (err: any) {
      ElMessage.error(err.response?.data?.message || '取消任务失败')
    } finally {
      task.isCancelling = false
    }
  }

  const cancelCurrentTask = async () => {
    if (currentViewTaskId.value) {
      await cancelTask(currentViewTaskId.value)
    } else if (currentTaskId.value) {
      await cancelTask(currentTaskId.value)
    }
  }

  // ---------------------------------------------------------------------------
  // 重试任务
  // ---------------------------------------------------------------------------
  const retryTask = async (taskId: string) => {
    const task = recentTasks.value.find((t) => t.taskId === taskId)
    if (!task) {
      ElMessage.warning('任务不存在')
      return
    }
    const formData = taskFormDataMap.get(taskId)
    if (!formData) {
      ElMessage.warning('该任务已超过当前会话，无法重试，请重新上传文件')
      return
    }

    const idx = recentTasks.value.findIndex((t) => t.taskId === taskId)
    if (idx !== -1) recentTasks.value.splice(idx, 1)

    const newTaskId = await startTask(formData, { visible: true })
    ElMessage.success('任务已重新提交')
    return newTaskId
  }

  // ---------------------------------------------------------------------------
  // 加载已有任务结果（兼容旧接口）
  // ---------------------------------------------------------------------------
  const loadTaskResult = async (taskId: string) => {
    const res = await getStatus(taskId)
    const { result, creator_name, creator_emp_id, created_at, model_name, processing_seconds } = res.data.data
    if (result) {
      taskResult.value = { ...result, created_at, model_name, processing_seconds }
      currentTaskId.value = taskId
      currentCreatorName.value = creator_name || ''
      currentCreatorEmpId.value = creator_emp_id || ''
    }
    return !!result
  }

  // ---------------------------------------------------------------------------
  // 页面刷新后恢复进行中的任务 + 最近完成的任务
  // ---------------------------------------------------------------------------
  const restoreRunningTasks = async () => {
    try {
      // 1. 恢复 running 任务（后端对游客返回 completed，直接放入 recentTasks）
      const res = await getRunningTasks()
      if (res.data.code === 200) {
        const tasks = res.data.data || []
        for (const t of tasks) {
          if (getTaskById(t.task_id)) continue

          const task: RunningTask = {
            taskId: t.task_id,
            fileName: `${t.file_a_name || '采购结果'} vs ${t.file_b_name || '合同'}`,
            status: t.status as RunningTask['status'],
            progress: t.progress || 0,
            message: t.message || '恢复轮询...',
            processMode: t.process_mode,
            startTime: t.created_at,
            visible: false,
          }

          // 已结束的任务直接放入 recentTasks，避免轮询
          if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
            recentTasks.value.unshift(task)
          } else {
            activeTasks.value.push(task)
            startPolling(t.task_id)
          }
        }
        // 限制 recentTasks 最多 20 条
        if (recentTasks.value.length > 20) {
          recentTasks.value = recentTasks.value.slice(0, 20)
        }
      }

      // 2. 恢复最近完成的 completed / failed / cancelled 任务
      const recordsRes = await getRecords({ page: 1, page_size: 20 })
      if (recordsRes.data.code === 200) {
        const records = recordsRes.data.data.list || []
        const newRecents: RunningTask[] = []
        for (const r of records) {
          if (getTaskById(r.task_id)) continue
          if (r.status === 'pending' || r.status === 'processing') continue

          const task: RunningTask = {
            taskId: r.task_id,
            fileName: r.project_name || '未命名项目',
            status: r.status as RunningTask['status'],
            progress: r.status === 'completed' ? 100 : 0,
            message: r.status === 'completed' ? '比对任务已完成' : (r.conclusion || '任务已结束'),
            startTime: r.created_at || new Date().toISOString(),
            visible: false,
          }
          newRecents.push(task)
        }
        // 合并到 recentTasks，去重
        const merged = [...newRecents, ...recentTasks.value]
        const seen = new Set<string>()
        recentTasks.value = merged.filter((t) => {
          if (seen.has(t.taskId)) return false
          seen.add(t.taskId)
          return true
        })
        // 限制最多 20 条
        if (recentTasks.value.length > 20) {
          recentTasks.value = recentTasks.value.slice(0, 20)
        }
      }
    } catch (_err) {
      // 静默失败
    }
  }

  // ---------------------------------------------------------------------------
  // 清理（兼容旧接口）
  // ---------------------------------------------------------------------------
  const clearCompareInterval = () => {
    activeTasks.value.forEach((t) => clearTaskInterval(t))
  }

  const resetCompareState = () => {
    clearCompareInterval()
    activeTasks.value = []
    recentTasks.value = []
    currentViewTaskId.value = ''
    taskResult.value = null
    currentTaskId.value = ''
    currentCreatorName.value = ''
    currentCreatorEmpId.value = ''
    taskFormDataMap.clear()
    // 释放所有 blob URL，防止内存泄漏
    contractBlobUrlMap.forEach((url) => URL.revokeObjectURL(url))
    contractBlobUrlMap.clear()
  }

  return {
    // 多任务队列
    activeTasks,
    recentTasks,
    currentViewTaskId,
    // 兼容旧接口
    isComparing,
    taskResult,
    currentTaskId,
    currentCreatorName,
    currentCreatorEmpId,
    hasReport,
    progressVisible,
    progressPercent,
    progressStatus,
    progressProcessMode,
    isCancelling,
    // 方法
    startTask,
    runBatchCompare,
    cancelTask,
    cancelCurrentTask,
    retryTask,
    loadTaskResult,
    restoreRunningTasks,
    showTaskProgress,
    hideTaskProgress,
    clearCompareInterval,
    resetCompareState,
    getContractBlobUrl,
  }
})
