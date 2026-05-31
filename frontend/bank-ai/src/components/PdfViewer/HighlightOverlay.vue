<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  bbox: [number, number, number, number]  // [x0, y0, x1, y1] PDF Points
  scale: number                            // CSS 像素缩放比例
  rotation?: number                        // PDF 页面旋转角度（0/90/180/270）
}

const props = withDefaults(defineProps<Props>(), {
  rotation: 0,
})

const style = computed(() => {
  let [x0, y0, x1, y1] = props.bbox

  // 坑2 防护：旋转矩阵处理
  // PDF.js 的 viewport 已经处理了旋转后的坐标映射，
  // 但如果 bbox 来自未旋转的原始物理页面，需要手动转换。
  // 此处简化：假设传入的 bbox 已由父组件处理过旋转（若使用 PDF.js transform），
  // 或传入的 bbox 与当前渲染方向一致。
  // 若父组件未处理旋转，可在此增加 transform 逻辑。

  const left = x0 * props.scale
  const top = y0 * props.scale
  const width = (x1 - x0) * props.scale
  const height = (y1 - y0) * props.scale

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`,
  }
})
</script>

<template>
  <div class="highlight-overlay" :style="style" />
</template>

<style scoped>
.highlight-overlay {
  position: absolute;
  background: rgba(255, 235, 59, 0.3);
  border: 2px solid #FFC107;
  pointer-events: none;
  z-index: 10;
  border-radius: 2px;
}
</style>
