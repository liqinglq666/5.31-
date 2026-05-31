<script setup lang="ts">
/**
 * Watermark.vue
 * -------------
 * 全局防泄密水印组件。
 * 使用 Canvas 绘制倾斜文字瓦片，铺满全屏；
 * 通过 MutationObserver 监控 DOM，若用户尝试删除或篡改水印节点，立即自动重建。
 * 仅在检测到登录 Token 后才显示。
 */

import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useUserStore } from '@/store'
import { useRoute } from 'vue-router'
import { formatDateTimeShort, pad } from '@/utils/format'

const WATERMARK_ID = 'bank-ai-watermark'

const watermarkUrl = ref('')
const userStore = useUserStore()
const route = useRoute()

let timer: number | null = null
let observer: MutationObserver | null = null

/**
 * 在 Canvas 上绘制单个水印瓦片并返回 base64 PNG
 */
const drawWatermark = (): string => {
  const canvas = document.createElement('canvas')
  const width = 480
  const height = 320
  canvas.width = width
  canvas.height = height

  const ctx = canvas.getContext('2d')
  if (!ctx) return ''

  // 清空画布
  ctx.clearRect(0, 0, width, height)

  // 字体与颜色：灰色、低透明度（0.085），若隐若现但不干扰阅读
  ctx.font = '500 15px "Microsoft YaHei", "PingFang SC", SimSun, sans-serif'
  ctx.fillStyle = 'rgba(100, 100, 100, 0.085)'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  // 移动到中心并倾斜 -30 度
  ctx.translate(width / 2, height / 2)
  ctx.rotate((-30 * Math.PI) / 180)

  const now = new Date()
  const timeStr = `${formatDateTimeShort(now)}:${pad(now.getSeconds())}`

  const text = `${userStore.userInfo?.full_name || ''} ${userStore.userInfo?.employee_id || ''} ${timeStr}`
  ctx.fillText(text, 0, 0)

  return canvas.toDataURL('image/png')
}

/**
 * 确保水印 DOM 节点存在且样式正确
 */
const ensureWatermarkNode = () => {
  let el = document.getElementById(WATERMARK_ID)

  // 若节点被删除，重新创建
  if (!el) {
    el = document.createElement('div')
    el.id = WATERMARK_ID
    document.body.appendChild(el)
  }

  // 在修改样式前短暂断开 Observer，防止自己修改自己触发无限循环
  if (observer) {
    observer.disconnect()
  }

  // 强制还原样式（防止通过控制台篡改 style）
  el.style.cssText = `
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 9999 !important;
    pointer-events: none !important;
    background-image: url(${watermarkUrl.value}) !important;
    background-repeat: repeat !important;
    opacity: 1 !important;
    display: block !important;
    visibility: visible !important;
  `

  // 重新连接 Observer
  if (observer) {
    observer.observe(document.body, { childList: true })
    observer.observe(el, {
      attributes: true,
      attributeFilter: ['style', 'class'],
    })
  }
}

/**
 * 启动 MutationObserver，防御删除与属性篡改
 */
const startObserver = () => {
  observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      // 监听 body 子节点变化：水印被删除时立即重建
      if (mutation.type === 'childList') {
        const removed = Array.from(mutation.removedNodes)
        const isRemoved = removed.some(
          (node) => (node as HTMLElement).id === WATERMARK_ID
        )
        if (isRemoved) {
          ensureWatermarkNode()
        }
      }

      // 监听水印节点自身属性变化：被篡改样式时立即还原
      if (mutation.type === 'attributes') {
        const target = mutation.target as HTMLElement
        if (target.id === WATERMARK_ID) {
          ensureWatermarkNode()
        }
      }
    })
  })

  // 观察 body 子节点列表
  observer.observe(document.body, { childList: true })

  // 观察水印节点属性
  const el = document.getElementById(WATERMARK_ID)
  if (el) {
    observer.observe(el, {
      attributes: true,
      attributeFilter: ['style', 'class'],
    })
  }
}

/**
 * 初始化水印：获取用户信息 -> 绘制 -> 挂载 -> 定时更新 -> 启动监控
 * 登录页不显示水印
 */
const initWatermark = () => {
  if (!userStore.isLoggedIn) {
    return
  }
  if (route.path === '/login') {
    return
  }

  if (!userStore.userInfo) {
    userStore.fetchUserInfo().then(() => {
      watermarkUrl.value = drawWatermark()
      ensureWatermarkNode()
    })
  } else {
    watermarkUrl.value = drawWatermark()
    ensureWatermarkNode()
  }

  timer = window.setInterval(() => {
    watermarkUrl.value = drawWatermark()
    ensureWatermarkNode()
  }, 1000)

  startObserver()
}

/**
 * 清理水印资源
 */
const destroyWatermark = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (observer) {
    observer.disconnect()
    observer = null
  }
  const el = document.getElementById(WATERMARK_ID)
  if (el) {
    el.remove()
  }
}

watch(
  () => userStore.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      initWatermark()
    } else {
      destroyWatermark()
    }
  },
  { immediate: true }
)

watch(
  () => route.path,
  (path) => {
    if (path === '/login') {
      destroyWatermark()
    } else if (userStore.isLoggedIn) {
      initWatermark()
    }
  }
)

onUnmounted(() => {
  destroyWatermark()
})
</script>

<template>
  <!-- 本组件不渲染任何 Vue 模板节点，水印 DOM 完全由脚本控制并挂载到 body -->
</template>
