<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, View, Message } from '@element-plus/icons-vue'
import { generateRectification } from '@/api/task'

const props = defineProps<{
  taskId?: string
}>()

const drawerVisible = ref(false)
const loading = ref(false)
const content = ref('')
const previewVisible = ref(false)

const open = () => {
  if (!props.taskId) {
    ElMessage.warning('请先完成任务比对')
    return
  }
  drawerVisible.value = true
  content.value = ''
  loading.value = true

  generateRectification(props.taskId, (chunk) => {
    content.value += chunk
  })
    .then(() => {
      ElMessage.success('整改函生成完毕')
    })
    .catch((err: any) => {
      ElMessage.error(err.message || '整改函生成失败')
    })
    .finally(() => {
      loading.value = false
    })
}

const copy = async () => {
  if (!content.value) return
  try {
    await navigator.clipboard.writeText(content.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const openPreview = () => {
  previewVisible.value = true
}

defineExpose({ open })
</script>

<template>
  <div class="rectification-letter">
    <!-- 整改函侧边栏 -->
    <el-drawer
      v-model="drawerVisible"
      title="AI 整改函生成"
      size="90%"
    :style="{ maxWidth: '560px' }"
      destroy-on-close
      append-to-body
    >
      <div class="rectification-drawer-body">
        <div class="rectification-paper">
          <div class="rectification-paper-title">合同合规整改告知函</div>
          <pre class="rectification-paper-content">{{ content || '正在生成中，请稍候...' }}</pre>
          <div v-if="loading" class="rectification-typing">
            <span class="typing-dot" />
            <span class="typing-dot" />
            <span class="typing-dot" />
          </div>
        </div>
        <div class="rectification-actions">
          <el-button :icon="CopyDocument" @click="copy"> 复制全文 </el-button>
          <el-button type="primary" :icon="View" @click="openPreview">
            预览公函
          </el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 预览公函弹窗 -->
    <el-dialog
      v-model="previewVisible"
      title="整改告知函预览"
      width="800px"
      align-center
    >
      <div class="preview-paper">
        <pre>{{ content || '暂无内容' }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.rectification-drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
}

.rectification-paper {
  flex: 1;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 20px;
  overflow-y: auto;
  margin-bottom: 16px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
}

.rectification-paper-title {
  font-size: 18px;
  font-weight: 700;
  text-align: center;
  color: #1e3a8a;
  margin-bottom: 16px;
  letter-spacing: 2px;
}

.rectification-paper-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.8;
  color: #334155;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  margin: 0;
}

.rectification-typing {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  animation: typing-bounce 1.4s infinite ease-in-out both;
}
.typing-dot:nth-child(1) {
  animation-delay: -0.32s;
}
.typing-dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes typing-bounce {
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.rectification-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.preview-paper {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 28px 32px;
  min-height: 400px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
}

.preview-paper pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 15px;
  line-height: 1.9;
  color: #1e293b;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  margin: 0;
}
</style>
