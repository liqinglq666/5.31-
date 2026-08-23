import api from './client'
import type { ApiResponse, RecordsResponse, TaskResult } from '@/types/api'
import { TOKEN_KEY } from '@/utils/constants'

export const getRecords = (params: {
  page: number
  page_size: number
  keyword?: string
  risk_level?: string
  scope?: string
  creator_id?: string
  is_archived?: boolean
}) => api.get<ApiResponse<RecordsResponse>>('/api/v1/records', { params })

export const exportExcel = (taskIds: string, responseType: 'blob' = 'blob') =>
  api.get('/api/v1/export/excel', {
    params: { task_ids: taskIds },
    responseType,
  })

export const addRemark = (taskId: string, remark: string) =>
  api.post<ApiResponse<{ task_id: string; remark: string; remark_time?: string }>>(
    `/api/v1/tasks/${taskId}/remark`,
    { remark }
  )

export const archiveTask = (taskId: string) =>
  api.post<ApiResponse<{ task_id: string; archive_time: string }>>(
    `/api/v1/tasks/${taskId}/archive`
  )

export const generateRectification = async (
  taskId: string,
  onChunk: (chunk: string) => void
) => {
  const token = localStorage.getItem(TOKEN_KEY) || ''

  const res = await fetch(
    `/api/v1/generate-rectification/${taskId}`,
    {
      method: 'POST',
      headers: {
        Authorization: token ? `Bearer ${token}` : '',
      },
    }
  )
  if (!res.ok) {
    const detail = await res.text().catch(() => '生成整改函失败')
    throw new Error(detail)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
  const decoder = new TextDecoder('utf-8')
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}

const PDF_EXPORT_OPTIONS = {
  margin: [14, 12, 14, 12] as [number, number, number, number],
  image: { type: 'jpeg' as const, quality: 0.98 },
  html2canvas: {
    scale: 2,
    useCORS: true,
    letterRendering: true,
    backgroundColor: '#ffffff',
  },
  jsPDF: {
    unit: 'mm' as const,
    format: 'a4' as const,
    orientation: 'portrait' as const,
  },
  pagebreak: { mode: ['css', 'legacy'] as string[] },
}

/** 为 PDF 添加红色水印 */
function addPdfWatermark(pdf: any) {
  const totalPages = pdf.internal.getNumberOfPages()
  const pageWidth = pdf.internal.pageSize.getWidth()
  for (let i = 1; i <= totalPages; i++) {
    pdf.setPage(i)
    pdf.setFontSize(10)
    pdf.setTextColor(192, 0, 0)
    pdf.text('智契 AI - 秘密级文件', pageWidth / 2, 8, {
      align: 'center',
    })
  }
}

/** 准备 DOM 元素用于 PDF 导出（隐藏干扰元素） */
function prepareElementForExport(reportElement: HTMLElement) {
  reportElement.classList.add('pdf-exporting')
  const stickyElements = reportElement.querySelectorAll<HTMLElement>(
    '.report-sticky-footer, .ai-assistant, .report-anchor'
  )
  const originalDisplays: Map<HTMLElement, string> = new Map()
  stickyElements.forEach((el) => {
    originalDisplays.set(el, el.style.display)
    el.style.display = 'none'
  })
  return () => {
    reportElement.classList.remove('pdf-exporting')
    stickyElements.forEach((el) => {
      el.style.display = originalDisplays.get(el) || ''
    })
  }
}

export const exportReportPdf = async (
  reportElement: HTMLElement,
  filename?: string
) => {
  const html2pdf = (await import('html2pdf.js')).default
  const restore = prepareElementForExport(reportElement)

  try {
    const pdf = await html2pdf()
      .set({ ...PDF_EXPORT_OPTIONS, filename: filename || `合规审查报告_${new Date().getTime()}.pdf` })
      .from(reportElement)
      .toPdf()
      .get('pdf')
    addPdfWatermark(pdf)
    pdf.save(filename || `合规审查报告_${new Date().getTime()}.pdf`)
  } finally {
    restore()
  }
}

/** 导出报告为 Blob，不触发下载 */
export const exportReportPdfToBlob = async (
  reportElement: HTMLElement
): Promise<Blob> => {
  const html2pdf = (await import('html2pdf.js')).default
  const restore = prepareElementForExport(reportElement)

  try {
    const pdf = await html2pdf()
      .set(PDF_EXPORT_OPTIONS)
      .from(reportElement)
      .toPdf()
      .get('pdf')
    addPdfWatermark(pdf)
    return pdf.output('blob')
  } finally {
    restore()
  }
}
