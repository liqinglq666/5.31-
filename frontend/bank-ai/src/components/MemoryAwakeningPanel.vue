<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps<{
  supplierContext: string
  ragContext: string
}>()

const isNoHistory = computed(() =>
  props.supplierContext.includes('首次审查')
)

const displayLines = ref<string[]>([])
const isTypingDone = ref(false)

let timer: ReturnType<typeof setInterval> | null = null

const startTyping = () => {
  displayLines.value = []
  isTypingDone.value = false

  const lines = isNoHistory.value
    ? ['🔍 已连通卷宗库：未发现该供应商历史劣迹，已启动实时合规监控。']
    : [
        '🔍 已连通 PostgreSQL 核心卷宗库...',
        `💡 提取到供应商画像：${props.supplierContext}`,
        `⚠️ 触发条款预警：${props.ragContext}`,
      ]

  let lineIndex = 0
  let charIndex = 0

  timer = setInterval(() => {
    if (lineIndex >= lines.length) {
      isTypingDone.value = true
      if (timer) {
        clearInterval(timer)
        timer = null
      }
      return
    }

    const currentLine = lines[lineIndex]
    if (!currentLine) {
      lineIndex++
      charIndex = 0
      return
    }
    if (charIndex === 0) {
      displayLines.value.push('')
    }

    if (charIndex < currentLine.length) {
      displayLines.value[lineIndex] = (displayLines.value[lineIndex] ?? '') + currentLine.charAt(charIndex)
      charIndex++
    } else {
      lineIndex++
      charIndex = 0
    }
  }, 28)
}

watch(
  () => [props.supplierContext, props.ragContext],
  () => {
    if (timer) clearInterval(timer)
    startTyping()
  },
  { immediate: true }
)

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="memory-awakening-panel">
    <div class="memory-header">
      <span class="memory-icon">💾</span>
      <span class="memory-title">全息历史数据库唤醒</span>
      <span class="memory-pulse" />
    </div>
    <div class="memory-body">
      <div
        v-for="(line, idx) in displayLines"
        :key="idx"
        class="typewriter-line"
      >
        {{ line }}<span v-if="!isTypingDone && idx === displayLines.length - 1" class="cursor">|</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-awakening-panel {
  background: linear-gradient(135deg, #f5f3ff 0%, #e0e7ff 100%);
  border: 1px solid #c4b5fd;
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 22px;
  position: relative;
  overflow: hidden;
}

.memory-awakening-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, #8b5cf6 0%, #6366f1 100%);
}

.memory-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.memory-icon {
  font-size: 22px;
  animation: pulse 2s ease-in-out infinite;
  display: inline-block;
}

.memory-title {
  font-size: 15px;
  font-weight: 700;
  color: #5b21b6;
  letter-spacing: 0.5px;
}

.memory-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #8b5cf6;
  margin-left: auto;
  animation: pulse-dot 2s ease-in-out infinite;
}

.memory-body {
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  padding-left: 4px;
}

.typewriter-line {
  font-size: 13px;
  line-height: 1.9;
  color: #4c1d95;
  min-height: 1.9em;
  word-break: break-word;
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 1.1em;
  background: #7c3aed;
  margin-left: 2px;
  animation: blink 0.9s step-end infinite;
  vertical-align: text-bottom;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.75;
  }
}

@keyframes pulse-dot {
  0%,
  100% {
    opacity: 1;
    box-shadow: 0 0 0 0 rgba(139, 92, 246, 0.5);
  }
  50% {
    opacity: 0.7;
    box-shadow: 0 0 0 6px rgba(139, 92, 246, 0);
  }
}
</style>
