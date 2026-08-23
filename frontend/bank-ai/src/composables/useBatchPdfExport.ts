import { ref, nextTick } from 'vue'
import { createApp, h } from 'vue'
import JSZip from 'jszip'
import { ElMessage } from 'element-plus'
import { exportReportPdfToBlob } from '@/api/task'
import { getStatus } from '@/api/compare'
import BatchReportTemplate from '@/components/BatchReportTemplate.vue'
import type { RecordItem, TaskResult } from '@/types/api'

export interface BatchExportItem {
  record: RecordItem
  status: 'pending' | 'processing' | 'success' | 'error'
  message?: string
}

export function useBatchPdfExport() {
  const visible = ref(false)
  const items = ref<BatchExportItem[]>([])
  const currentIndex = ref(0)
  const isRunning = ref(false)
  const cancelled = ref(false)

  const startExport = async (records: RecordItem[]) => {
    if (isRunning.value) return
    if (records.length === 0) {
      ElMessage.warning('请先在表格中勾选需要导出的记录')
      return
    }

    isRunning.value = true
    cancelled.value = false
    visible.value = true
    currentIndex.value = 0

    items.value = records.map((r) => ({
      record: r,
      status: 'pending',
    }))

    const zip = new JSZip()
    const failedItems: BatchExportItem[] = []

    for (let i = 0; i < records.length; i++) {
      if (cancelled.value) break
      currentIndex.value = i

      const record = records[i]!
      const item = items.value[i]!
      item.status = 'processing'

      try {
        // 1. 获取任务结果
        const res = await getStatus(record.task_id)
        const {
          result,
          creator_name,
          creator_emp_id,
          created_at,
          model_name,
          processing_seconds,
        } = res.data.data

        if (!result) {
          throw new Error('该记录暂无比对结果')
        }

        const taskResult: TaskResult = {
          ...result,
          created_at,
          model_name,
          processing_seconds,
        }

        // 2. 创建离屏容器
        const container = document.createElement('div')
        container.style.position = 'fixed'
        container.style.left = '-9999px'
        container.style.top = '0'
        container.style.width = '1200px'
        document.body.appendChild(container)

        // 3. 挂载报告组件
        const app = createApp(
          h(BatchReportTemplate, {
            taskResult,
            creatorName: creator_name || '',
            creatorEmpId: creator_emp_id || '',
          })
        )
        app.mount(container)

        // 4. 等待 DOM 渲染完成
        await nextTick()
        await new Promise((r) => setTimeout(r, 400))

        // 5. 生成 PDF Blob
        const reportEl = container.querySelector('.batch-report-body') as HTMLElement
        if (!reportEl) {
          throw new Error('报告元素未找到')
        }
        const blob = await exportReportPdfToBlob(reportEl)

        // 6. 添加到 ZIP
        const safeName = sanitizeFileName(record.project_name || record.task_id)
        zip.file(`${safeName}_审查报告.pdf`, blob)

        // 7. 清理
        app.unmount()
        document.body.removeChild(container)

        item.status = 'success'

        // 小间隔避免浏览器卡顿
        if (i < records.length - 1) {
          await new Promise((r) => setTimeout(r, 300))
        }
      } catch (err: any) {
        item.status = 'error'
        item.message = err.message || '生成失败'
        failedItems.push(item)
      }
    }

    // 8. 生成并下载 ZIP
    if (!cancelled.value) {
      try {
        const zipBlob = await zip.generateAsync({ type: 'blob' })
        const url = URL.createObjectURL(zipBlob)
        const link = document.createElement('a')
        link.href = url
        const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
        link.download = `批量审查报告_${dateStr}.zip`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)

        if (failedItems.length > 0) {
          ElMessage.warning(
            `批量导出完成，其中 ${failedItems.length} 条记录生成失败，已自动跳过`
          )
        } else {
          ElMessage.success('批量导出成功')
        }
      } catch (_err) {
        ElMessage.error('ZIP 打包失败')
      }
    } else {
      ElMessage.info('已取消批量导出')
    }

    isRunning.value = false
    return { failedItems }
  }

  const cancel = () => {
    if (isRunning.value) {
      cancelled.value = true
    }
  }

  const close = () => {
    if (!isRunning.value) {
      visible.value = false
    }
  }

  return {
    visible,
    items,
    currentIndex,
    isRunning,
    startExport,
    cancel,
    close,
  }
}

function sanitizeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
}
