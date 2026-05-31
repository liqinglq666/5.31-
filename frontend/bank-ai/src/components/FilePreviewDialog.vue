<script setup lang="ts">
/**
 * FilePreviewDialog.vue
 * ---------------------
 * 通用文件在线预览侧边面板组件。
 * 从左侧滑出，支持拖拽调整宽度，不遮挡右侧报告区域，方便左右对比。
 * 支持格式：PDF（iframe 内嵌）、DOCX（docx-preview 渲染）、TXT（pre 纯文本）。
 */

import { ref, watch, nextTick, onUnmounted } from 'vue'
import { renderAsync } from 'docx-preview'
import { FullScreen, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  visible: boolean
  file: File | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const isFullscreen = ref(false)
const loading = ref(false)
const fileType = ref<'pdf' | 'docx' | 'txt' | 'unknown'>('unknown')

// PDF / TXT 内容
const txtContent = ref('')
const blobUrl = ref('')

// DOCX 渲染容器
const docxContainerRef = ref<HTMLElement | null>(null)
const docxContainerFullscreenRef = ref<HTMLElement | null>(null)

// 面板宽度（默认 45%）
const panelWidth = ref(45)
const MIN_WIDTH = 30
const MAX_WIDTH = 70

// 拖拽相关
const isResizing = ref(false)
const startX = ref(0)
const startWidth = ref(45)

watch(
  () => props.visible,
  async (val) => {
    if (val) {
      await openPreview()
    } else {
      cleanup()
    }
  }
)

// 监听全屏切换，DOCX 需要重新渲染
watch(isFullscreen, async (val) => {
  if (props.visible && props.file && fileType.value === 'docx') {
    await nextTick()
    await renderDocx(props.file)
  }
})

const closePanel = () => {
  emit('update:visible', false)
}

// 开始拖拽
const startResize = (e: MouseEvent) => {
  isResizing.value = true
  startX.value = e.clientX
  startWidth.value = panelWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

// 拖拽中
const onResize = (e: MouseEvent) => {
  if (!isResizing.value) return
  const deltaX = e.clientX - startX.value
  const deltaPercent = (deltaX / window.innerWidth) * 100
  let newWidth = startWidth.value + deltaPercent
  // 限制范围
  newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth))
  panelWidth.value = newWidth
}

// 结束拖拽
const stopResize = () => {
  if (isResizing.value) {
    isResizing.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
}

// 全局监听拖拽事件
window.addEventListener('mousemove', onResize)
window.addEventListener('mouseup', stopResize)

onUnmounted(() => {
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
})

/**
 * 根据扩展名判断文件类型并执行对应预览逻辑
 */
const openPreview = async () => {
  if (!props.file) return
  cleanup()
  loading.value = true

  const ext = props.file.name.split('.').pop()?.toLowerCase() || ''

  if (ext === 'pdf') {
    fileType.value = 'pdf'
    blobUrl.value = URL.createObjectURL(props.file)
  } else if (ext === 'docx') {
    fileType.value = 'docx'
    // 等待 DOM 更新后再渲染 DOCX
    await nextTick()
    await renderDocx(props.file)
  } else if (ext === 'txt') {
    fileType.value = 'txt'
    await readTxt(props.file)
  } else {
    fileType.value = 'unknown'
    ElMessage.warning('暂不支持的预览格式')
  }

  loading.value = false
}

/**
 * 使用 docx-preview 渲染 DOCX 文件到指定容器
 */
const renderDocxToContainer = async (file: File, container: HTMLElement | null) => {
  if (!container) return
  const arrayBuffer = await file.arrayBuffer()
  container.innerHTML = ''
  await renderAsync(
    arrayBuffer,
    container,
    undefined,
    {
      className: 'docx-preview',
      inWrapper: false,
    }
  )
}

/**
 * 渲染 DOCX 到当前可见的容器
 */
const renderDocx = async (file: File) => {
  await nextTick()
  if (isFullscreen.value && docxContainerFullscreenRef.value) {
    await renderDocxToContainer(file, docxContainerFullscreenRef.value)
  } else if (docxContainerRef.value) {
    await renderDocxToContainer(file, docxContainerRef.value)
  }
}

/**
 * 读取 TXT 文件内容
 */
const readTxt = (file: File): Promise<void> => {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      txtContent.value = (e.target?.result as string) || ''
      resolve()
    }
    reader.onerror = () => {
      ElMessage.error('文本读取失败')
      resolve()
    }
    reader.readAsText(file)
  })
}

/**
 * 清理资源：释放 Blob URL、清空 DOCX 容器
 */
const cleanup = () => {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
  txtContent.value = ''
  if (docxContainerRef.value) {
    docxContainerRef.value.innerHTML = ''
  }
  if (docxContainerFullscreenRef.value) {
    docxContainerFullscreenRef.value.innerHTML = ''
  }
}
</script>

<template>
  <Teleport to="body">
    <!-- 左侧预览面板 -->
    <Transition name="slide">
      <div
        v-show="visible && !isFullscreen"
        class="preview-panel"
        :style="{ width: `${panelWidth}%` }"
      >
        <!-- 拖拽手柄 -->
        <div
          class="resize-handle"
          :class="{ 'is-resizing': isResizing }"
          @mousedown="startResize"
          title="拖动调整宽度"
        >
          <div class="resize-line"></div>
          <div class="resize-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>

        <!-- 头部 -->
        <div class="panel-header">
          <div class="header-left">
            <span class="panel-title">在线预览</span>
            <span class="file-name" :title="file?.name">{{ file?.name || '' }}</span>
          </div>
          <div class="header-actions">
            <el-button
              type="primary"
              text
              :icon="FullScreen"
              @click="isFullscreen = true"
            >
              全屏
            </el-button>
            <el-button
              type="info"
              text
              :icon="Close"
              @click="closePanel"
            >
              关闭
            </el-button>
          </div>
        </div>

        <!-- 内容区 -->
        <div v-loading="loading" class="panel-body">
          <!-- PDF 预览 -->
          <iframe
            v-if="fileType === 'pdf' && blobUrl"
            :src="blobUrl"
            class="preview-iframe"
            frameborder="0"
          ></iframe>

          <!-- DOCX 预览 -->
          <div
            v-else-if="fileType === 'docx'"
            ref="docxContainerRef"
            class="preview-docx"
          />

          <!-- TXT 预览 -->
          <pre v-else-if="fileType === 'txt'" class="preview-txt">{{ txtContent }}</pre>

          <!-- 不支持的格式 -->
          <el-empty
            v-else
            description="暂不支持该格式的在线预览"
          />
        </div>
      </div>
    </Transition>

    <!-- 全屏模式 -->
    <Transition name="fade">
      <div
        v-show="visible && isFullscreen"
        class="preview-fullscreen"
      >
        <!-- 头部 -->
        <div class="panel-header">
          <div class="header-left">
            <span class="panel-title">在线预览</span>
            <span class="file-name" :title="file?.name">{{ file?.name || '' }}</span>
          </div>
          <div class="header-actions">
            <el-button
              type="primary"
              text
              :icon="FullScreen"
              @click="isFullscreen = false"
            >
              退出全屏
            </el-button>
            <el-button
              type="info"
              text
              :icon="Close"
              @click="closePanel"
            >
              关闭
            </el-button>
          </div>
        </div>

        <!-- 内容区 -->
        <div v-loading="loading" class="panel-body">
          <!-- PDF 预览 -->
          <iframe
            v-if="fileType === 'pdf' && blobUrl"
            :src="blobUrl"
            class="preview-iframe"
            frameborder="0"
          ></iframe>

          <!-- DOCX 预览 -->
          <div
            v-else-if="fileType === 'docx'"
            ref="docxContainerFullscreenRef"
            class="preview-docx"
          />

          <!-- TXT 预览 -->
          <pre v-else-if="fileType === 'txt'" class="preview-txt">{{ txtContent }}</pre>

          <!-- 不支持的格式 -->
          <el-empty
            v-else
            description="暂不支持该格式的在线预览"
          />
        </div>
      </div>
    </Transition>

    <!-- 遮罩层（仅非全屏时显示，用于点击关闭） -->
    <Transition name="fade">
      <div
        v-show="visible && !isFullscreen"
        class="preview-backdrop"
        @click="closePanel"
      />
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 左侧预览面板 */
.preview-panel {
  position: fixed;
  top: 64px;
  left: 220px;
  height: calc(100vh - 64px);
  background: #fff;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.08);
}

/* 拖拽手柄 */
.resize-handle {
  position: absolute;
  right: -12px;
  top: 0;
  bottom: 0;
  width: 24px;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
  transition: background 0.2s;
}

.resize-handle:hover .resize-line,
.resize-handle.is-resizing .resize-line {
  background: #1e3a8a;
  width: 3px;
}

.resize-handle:hover .resize-dots span,
.resize-handle.is-resizing .resize-dots span {
  background: #1e3a8a;
}

.resize-line {
  width: 2px;
  height: 100%;
  background: transparent;
  transition: all 0.2s;
}

.resize-dots {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: none;
}

.resize-dots span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #c9cdd4;
  transition: background 0.2s;
}

/* 全屏模式 */
.preview-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: #fff;
  z-index: 2000;
  display: flex;
  flex-direction: column;
}

/* 头部 */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #f0f2f5;
  background: #fff;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  flex-shrink: 0;
}

.file-name {
  font-size: 13px;
  color: #86909c;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* 内容区 */
.panel-body {
  flex: 1;
  overflow: auto;
  background: #f7f8fa;
  padding: 16px;
}

.preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 8px;
  background: #fff;
}

.preview-docx {
  padding: 24px;
  background: #fff;
  border-radius: 8px;
  min-height: 100%;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
}

.preview-txt {
  padding: 24px;
  background: #fff;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Microsoft YaHei', 'PingFang SC', monospace;
  font-size: 14px;
  line-height: 1.8;
  color: #334155;
  min-height: 100%;
  margin: 0;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
}

/* 遮罩层 */
.preview-backdrop {
  position: fixed;
  top: 64px;
  left: 220px;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.15);
  z-index: 999;
}

/* 滑入动画 */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}

/* 淡入动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
