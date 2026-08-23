<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import HighlightOverlay from './HighlightOverlay.vue'
import type { VisualEvidence } from '@/types/api'

// PDF.js worker（Vite 环境下需要显式设置 worker 路径）
// 实际使用时需确保 pdfjs-dist 的 worker 文件可被访问
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

interface Props {
  url: string                              // PDF Blob URL 或静态路径
  highlight?: VisualEvidence | null        // 高亮坐标证据
}

const props = defineProps<Props>()

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const pdfDoc = ref<PDFDocumentProxy | null>(null)
const currentPage = ref(1)
const totalPages = ref(0)
const pageRotation = ref(0)
const cssScale = ref(1)
const isLoading = ref(false)

// 渲染指定页面
async function renderPage(pageNum: number) {
  if (!pdfDoc.value || !canvasRef.value || !containerRef.value) return
  isLoading.value = true

  try {
    const page: PDFPageProxy = await pdfDoc.value.getPage(pageNum)
    const viewport = page.getViewport({ scale: 1.0 })
    pageRotation.value = viewport.rotation

    // 坑5 防护 + 坑2 防护：计算基于 CSS 容器宽度的缩放比例
    const containerWidth = containerRef.value.clientWidth
    const baseScale = containerWidth / viewport.width
    const renderViewport = page.getViewport({ scale: baseScale })

    const canvas = canvasRef.value
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 处理高分屏 DPR：canvas 物理像素 = CSS 逻辑像素 × DPR
    const dpr = window.devicePixelRatio || 1
    canvas.width = renderViewport.width * dpr
    canvas.height = renderViewport.height * dpr
    canvas.style.width = `${renderViewport.width}px`
    canvas.style.height = `${renderViewport.height}px`

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    await page.render({
      canvasContext: ctx,
      viewport: renderViewport,
    }).promise

    cssScale.value = baseScale
    currentPage.value = pageNum
  } catch (err) {
    console.error('[PdfViewer] 渲染失败:', err)
  } finally {
    isLoading.value = false
  }
}

// 加载 PDF
async function loadPdf(url: string) {
  try {
    isLoading.value = true
    pdfDoc.value = await pdfjsLib.getDocument(url).promise
    totalPages.value = pdfDoc.value.numPages
    await renderPage(1)
  } catch (err) {
    console.error('[PdfViewer] PDF 加载失败:', err)
  }
}

// 监听 url 变化
watch(() => props.url, (newUrl) => {
  if (newUrl) {
    loadPdf(newUrl)
  }
}, { immediate: true })

// 监听高亮变化 → 翻页并显示
watch(() => props.highlight, async (ev) => {
  if (!ev) return
  const targetPage = ev.page_index + 1  // 0-based → 1-based
  if (targetPage !== currentPage.value && targetPage >= 1 && targetPage <= totalPages.value) {
    await renderPage(targetPage)
  } else {
    // 同一页也需要重新计算 scale（窗口大小可能变化）
    await nextTick()
    const containerWidth = containerRef.value?.clientWidth || 0
    if (containerWidth > 0) {
      const page = await pdfDoc.value?.getPage(targetPage)
      if (page) {
        const viewport = page.getViewport({ scale: 1.0 })
        cssScale.value = containerWidth / viewport.width
      }
    }
  }
})

onUnmounted(() => {
  pdfDoc.value?.destroy().catch(() => {})
})

function prevPage() {
  if (currentPage.value > 1) renderPage(currentPage.value - 1)
}

function nextPage() {
  if (currentPage.value < totalPages.value) renderPage(currentPage.value + 1)
}

// 若 highlight 存在，计算旋转后的 bbox（如果未在父层处理）
const displayBbox = computed(() => {
  if (!props.highlight) return null
  let [x0, y0, x1, y1] = props.highlight.bbox

  // 当页面有旋转时，利用 PDF.js 的 transform 矩阵转换坐标
  // 注意：此逻辑仅在已知 viewport 时才有效，此处简化处理
  // 若父组件已传入旋转后的 bbox，可直接透传
  if (pageRotation.value !== 0 && pdfDoc.value) {
    // 异步获取 viewport 在此不易处理，建议在渲染时同步计算
    // 此处仅作占位提示，实际转换应在 renderPage 中完成
  }

  return [x0, y0, x1, y1] as [number, number, number, number]
})
</script>

<template>
  <div class="pdf-viewer">
    <div v-if="isLoading" class="pdf-loading">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <span>PDF 加载中...</span>
    </div>

    <div ref="containerRef" class="pdf-canvas-container">
      <canvas ref="canvasRef" />
      <HighlightOverlay
        v-if="highlight && displayBbox"
        :bbox="displayBbox"
        :scale="cssScale"
        :rotation="pageRotation"
      />
    </div>

    <div v-if="totalPages > 0" class="pdf-toolbar">
      <el-button size="small" @click="prevPage" :disabled="currentPage <= 1">上一页</el-button>
      <span class="pdf-page-info">{{ currentPage }} / {{ totalPages }}</span>
      <el-button size="small" @click="nextPage" :disabled="currentPage >= totalPages">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.pdf-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
}

.pdf-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 12px;
  color: #909399;
}

.pdf-canvas-container {
  position: relative;
  flex: 1;
  overflow: auto;
  display: flex;
  justify-content: center;
  padding: 16px;
}

.pdf-canvas-container canvas {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  background: #fff;
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
}

.pdf-page-info {
  font-size: 14px;
  color: #606266;
  min-width: 60px;
  text-align: center;
}
</style>
