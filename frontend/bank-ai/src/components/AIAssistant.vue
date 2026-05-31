<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Promotion, MagicStick, Loading, Search, Warning } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import VueMarkdown from 'vue-markdown-render'
import api from '@/api'
import { TOKEN_KEY } from '@/utils/constants'
import { useModelStore } from '@/store'
import { useUserStore } from '@/store'
import ModelSelector from '@/components/ModelSelector.vue'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface CopilotSuggestion {
  text: string
  action?: string
}

interface CopilotContext {
  greeting: string
  context_summary: string
  suggestions: CopilotSuggestion[]
}

const route = useRoute()
const modelStore = useModelStore()
const userStore = useUserStore()

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
const props = defineProps<{
  taskId?: string
}>()

// ---------------------------------------------------------------------------
// 抽屉状态
// ---------------------------------------------------------------------------
const drawerVisible = ref(false)

// ---------------------------------------------------------------------------
// 聊天状态
// ---------------------------------------------------------------------------
const inputMessage = ref('')
const messages = ref<ChatMessage[]>([])
const isLoading = ref(false)
const isStreaming = ref(false)
const messagesContainerRef = ref<HTMLElement | null>(null)
const enableSearch = ref(false)
const thinkingSeconds = ref(0)
let thinkingTimer: ReturnType<typeof setInterval> | null = null

const startThinkingTimer = () => {
  thinkingSeconds.value = 0
  if (thinkingTimer) clearInterval(thinkingTimer)
  thinkingTimer = setInterval(() => {
    thinkingSeconds.value++
  }, 1000)
}

const stopThinkingTimer = () => {
  if (thinkingTimer) {
    clearInterval(thinkingTimer)
    thinkingTimer = null
  }
  thinkingSeconds.value = 0
}

// ---------------------------------------------------------------------------
// 连通性检查
// ---------------------------------------------------------------------------
const connectivityStatus = ref<'ok' | 'error' | 'checking'>('ok')

const checkConnectivity = async () => {
  connectivityStatus.value = 'checking'
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)
    const res = await fetch('/api/v1/stats', {
      method: 'GET',
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    if (res.ok) {
      connectivityStatus.value = 'ok'
    } else {
      connectivityStatus.value = 'error'
    }
  } catch (_err) {
    connectivityStatus.value = 'error'
  }
}

// ---------------------------------------------------------------------------
// Copilot 上下文
// ---------------------------------------------------------------------------
const copilotContext = ref<CopilotContext | null>(null)
const contextLoading = ref(false)

// ---------------------------------------------------------------------------
// 当前页面标识
// ---------------------------------------------------------------------------
const currentPageId = computed(() => {
  const routeName = route.name as string
  if (routeName === 'dashboard' || routeName === 'home') return 'dashboard'
  if (routeName === 'compare') return 'compare'
  if (routeName === 'records' || routeName === 'personal') return 'records'
  if (routeName === 'audit') return 'audit'
  return 'dashboard'
})

// ---------------------------------------------------------------------------
// 打开/关闭抽屉
// ---------------------------------------------------------------------------
const openDrawer = () => {
  if (userStore.isGuest) {
    ElMessage.warning('游客模式暂不支持使用智契 Copilot，请注册登录后使用')
    return
  }
  drawerVisible.value = true
  if (messages.value.length === 0) {
    loadCopilotContext()
  }
  checkConnectivity()
}

const closeDrawer = () => {
  drawerVisible.value = false
}

// ---------------------------------------------------------------------------
// 加载 Copilot 上下文
// ---------------------------------------------------------------------------
const loadCopilotContext = async () => {
  contextLoading.value = true
  try {
    const res = await api.get('/api/v1/copilot/context-chat', {
      params: {
        page_id: currentPageId.value,
        item_id: props.taskId || undefined,
      },
    })

    if (res.data.data) {
      copilotContext.value = res.data.data
      // 初始化欢迎消息
      messages.value = [
        {
          role: 'assistant',
          content: `**${res.data.data.greeting}**\n\n${res.data.data.context_summary}`,
        },
      ]
    }
  } catch (_err) {
    // 使用默认欢迎消息
    messages.value = [
      {
        role: 'assistant',
        content: '您好！我是您的合同审查助手。我可以帮您解读合同风险、分析比对结果、生成整改建议。有什么可以帮助您的吗？',
      },
    ]
  } finally {
    contextLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 滚动到底部
// ---------------------------------------------------------------------------
const scrollToBottom = async () => {
  await nextTick()
  const container = messagesContainerRef.value
  if (container) {
    container.scrollTop = container.scrollHeight
  }
}

watch(() => messages.value.length, scrollToBottom)

// ---------------------------------------------------------------------------
// 点击建议快捷输入
// ---------------------------------------------------------------------------
const applySuggestion = (suggestion: CopilotSuggestion) => {
  inputMessage.value = suggestion.text
  sendMessage()
}

// ---------------------------------------------------------------------------
// SSE 解析器：兼容纯文本流与标准 SSE 格式（data: xxx\n\n）
// ---------------------------------------------------------------------------
function parseSSEChunk(chunk: string): string {
  const lines = chunk.split('\n')
  const result: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('data:')) {
      const data = trimmed.slice(5).trim()
      if (data === '[DONE]') continue
      try {
        const obj = JSON.parse(data)
        result.push(obj.text || obj.content || obj.message || obj.delta || '')
      } catch {
        result.push(data)
      }
    } else if (trimmed && !trimmed.startsWith('event:') && !trimmed.startsWith('id:') && !trimmed.startsWith(':')) {
      // 纯文本流兼容
      result.push(trimmed)
    }
  }
  return result.join('')
}

// ---------------------------------------------------------------------------
// 发送消息 —— SSE 流式输出
// ---------------------------------------------------------------------------
const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!text) return

  if (connectivityStatus.value === 'error') {
    ElMessage.warning('网络连接异常，请检查后端服务')
    return
  }

  await checkConnectivity()
  if (connectivityStatus.value === 'error') {
    ElMessage.warning('网络连接异常，请检查后端服务')
    return
  }

  // 添加用户消息
  messages.value.push({ role: 'user', content: text })
  inputMessage.value = ''
  isLoading.value = true
  isStreaming.value = false
  startThinkingTimer()
  await scrollToBottom()

  // 构建历史记录（保留最近 10 轮上下文）
  const history = messages.value.slice(-11, -1).map((m) => ({
    role: m.role,
    content: m.content,
  }))

  // 预先插入一个空的 AI 消息占位
  const aiMessage: ChatMessage = { role: 'assistant', content: '' }
  messages.value.push(aiMessage)

  const token = localStorage.getItem(TOKEN_KEY) || ''

  try {
    // 如果有 taskId，使用文档问答接口，否则使用通用聊天接口
    // 使用相对路径，让 Vite 代理自动转发到后端
    const endpoint = props.taskId
      ? '/api/v1/chat/document'
      : '/api/v1/chat/general'

    const body: any = props.taskId
      ? { task_id: props.taskId, message: text, history, search: enableSearch.value }
      : { message: text, history, page_id: currentPageId.value, search: enableSearch.value }

    if (modelStore.currentModelId) {
      body.model_id = modelStore.currentModelId
    }

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: '请求失败' }))
      aiMessage.content = `**请求出错：**${errData.detail || response.statusText}`
      return
    }

    if (!response.body) {
      aiMessage.content = '无法读取响应流'
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let done = false

    while (!done) {
      const { value, done: readerDone } = await reader.read()
      done = readerDone
      if (value) {
        const chunk = decoder.decode(value, { stream: !done })
        const parsed = parseSSEChunk(chunk)
        if (parsed) {
          messages.value[messages.value.length - 1].content += parsed
          isStreaming.value = true
          stopThinkingTimer()
          await scrollToBottom()
        }
      }
    }
  } catch (_err) {
    messages.value[messages.value.length - 1].content = '**网络错误：**请检查后端服务是否正常运行'
    stopThinkingTimer()
  } finally {
    isLoading.value = false
    isStreaming.value = false
    stopThinkingTimer()
    await scrollToBottom()
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// ---------------------------------------------------------------------------
// 监听 taskId 变化，重新加载上下文
// ---------------------------------------------------------------------------
watch(
  () => props.taskId,
  () => {
    if (drawerVisible.value) {
      loadCopilotContext()
    }
  }
)

// ---------------------------------------------------------------------------
// 监听路由变化，重新加载上下文
// ---------------------------------------------------------------------------
watch(
  () => route.name,
  () => {
    if (drawerVisible.value && messages.value.length > 0) {
      loadCopilotContext()
    }
  }
)
</script>

<template>
  <div class="ai-assistant">
    <!-- 悬浮展开按钮 -->
    <div class="float-btn" @click="openDrawer">
      <img src="/ai-icon.png" alt="AI" class="float-btn-icon" />
    </div>

    <!-- 智能副驾抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :with-header="false"
      size="90%"
      :style="{ maxWidth: '520px' }"
      :destroy-on-close="false"
      class="copilot-drawer"
      modal-class="copilot-modal"
    >
      <div class="copilot-container">
        <!-- 标题栏 -->
        <div class="copilot-header">
          <div class="header-title">
            <div class="header-icon">
              <img src="/ai-icon.png" alt="AI" class="header-icon-img" />
            </div>
            <div class="header-text">
              <span class="title-main">智契 Copilot</span>
              <span class="title-sub">AI 智能副驾</span>
            </div>
          </div>
          <el-button type="info" text circle size="small" @click="closeDrawer">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>

        <!-- 连通性状态条 -->
        <div v-if="connectivityStatus === 'error'" class="connectivity-bar error">
          <el-icon><Warning /></el-icon>
          <span>网络连接异常，请检查后端服务是否正常运行</span>
        </div>

        <!-- 模型选择器 -->
        <div class="copilot-model-bar">
          <ModelSelector v-model="modelStore.currentModelId" size="small" />
        </div>

        <!-- 消息区 -->
        <div ref="messagesContainerRef" class="copilot-body">
          <!-- 上下文加载中 -->
          <div v-if="contextLoading" class="context-loading">
            <div class="loading-pulse">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <p class="loading-text">正在分析当前页面上下文...</p>
          </div>

          <!-- 消息列表 -->
          <template v-else>
            <div
              v-for="(msg, index) in messages"
              :key="index"
              class="message-row"
              :class="msg.role"
            >
              <div class="message-bubble">
                <div v-if="msg.role === 'assistant'" class="message-avatar">
                  <img src="/ai-icon.png" alt="AI" class="message-avatar-img" />
                </div>
                <div class="message-content">
                  <VueMarkdown v-if="msg.role === 'assistant'" :source="msg.content" />
                  <template v-else>{{ msg.content }}</template>
                </div>
              </div>
            </div>

            <!-- 输入中指示器（思考中，还未开始接收流） -->
            <div
              v-if="isLoading && !isStreaming"
              class="message-row assistant"
            >
              <div class="message-bubble">
                <div class="message-avatar">
                  <img src="/ai-icon.png" alt="AI" class="message-avatar-img" />
                </div>
                <div class="thinking-indicator">
                  <el-icon class="thinking-spinner is-loading"><Loading /></el-icon>
                  <span class="thinking-text">智契正在思考中...（已思考{{ thinkingSeconds }}秒）</span>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 快捷建议区 -->
        <div v-if="copilotContext?.suggestions && !isLoading" class="copilot-suggestions">
          <div
            v-for="(suggestion, idx) in copilotContext.suggestions"
            :key="idx"
            class="suggestion-chip"
            @click="applySuggestion(suggestion)"
          >
            {{ suggestion.text }}
          </div>
        </div>

        <!-- 输入区 -->
        <div class="copilot-footer">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="2"
            placeholder="输入您的问题，按 Enter 发送..."
            resize="none"
            :disabled="isLoading || contextLoading"
            @keydown="handleKeydown"
          />
          <div class="input-toolbar">
            <el-switch
              v-model="enableSearch"
              size="small"
              active-text="联网"
              inactive-text=""
            />
            <el-button
              type="primary"
              :disabled="!inputMessage.trim() || isLoading || contextLoading"
              @click="sendMessage"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.ai-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 999;
}

/* ---------------------------------------------------------------------------
   悬浮按钮
   --------------------------------------------------------------------------- */
.float-btn {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(30, 58, 138, 0.4);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  overflow: hidden;
}

.float-btn-icon {
  width: 40px;
  height: 40px;
  object-fit: contain;
}

.float-btn:hover {
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 12px 32px rgba(30, 58, 138, 0.5);
}

/* ---------------------------------------------------------------------------
   抽屉毛玻璃效果
   --------------------------------------------------------------------------- */
:deep(.copilot-drawer) {
  background: transparent !important;
}

:deep(.copilot-drawer .el-drawer) {
  background: rgba(255, 255, 255, 0.75) !important;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.1);
  border-left: 1px solid rgba(255, 255, 255, 0.5);
}

:deep(.copilot-modal) {
  background: rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(4px);
}

/* ---------------------------------------------------------------------------
   Copilot 容器
   --------------------------------------------------------------------------- */
.copilot-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.copilot-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: rgba(30, 58, 138, 0.9);
  backdrop-filter: blur(10px);
  color: #fff;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.header-icon-img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title-main {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.title-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

/* ---------------------------------------------------------------------------
   消息区
   --------------------------------------------------------------------------- */
.copilot-body {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: rgba(247, 248, 250, 0.5);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 上下文加载动画 */
.context-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 16px;
}

.loading-pulse {
  display: flex;
  align-items: center;
  gap: 6px;
}

.loading-pulse span {
  width: 10px;
  height: 10px;
  background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
  border-radius: 50%;
  animation: pulse 1.4s infinite ease-in-out both;
}

.loading-pulse span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-pulse span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes pulse {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.loading-text {
  font-size: 13px;
  color: #86909c;
}

/* 消息气泡 */
.message-row {
  display: flex;
  width: 100%;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 90%;
  display: flex;
  gap: 10px;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.message-avatar-img {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

.message-content {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-row.user .message-content {
  background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-row.assistant .message-content {
  background: rgba(255, 255, 255, 0.9);
  color: #1d2129;
  border: 1px solid rgba(229, 230, 235, 0.5);
  border-bottom-left-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* Markdown 样式 */
.message-content :deep(p) {
  margin: 0 0 8px 0;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message-content :deep(strong) {
  font-weight: 600;
  color: #1e3a8a;
}

.message-content :deep(code) {
  background: rgba(30, 58, 138, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
}

.message-content :deep(pre) {
  background: rgba(30, 58, 138, 0.05);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.message-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}

.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid #e5e6eb;
  padding: 8px 12px;
  text-align: left;
}

.message-content :deep(th) {
  background: rgba(30, 58, 138, 0.05);
  font-weight: 600;
}

/* 思考中指示器 */
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(30, 58, 138, 0.06);
  border-radius: 12px;
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(30, 58, 138, 0.08);
}

.thinking-text {
  font-size: 13px;
  color: #1e3a8a;
  font-weight: 500;
}

.thinking-spinner {
  font-size: 16px;
  color: #1e3a8a;
}

/* ---------------------------------------------------------------------------
   快捷建议
   --------------------------------------------------------------------------- */
.copilot-suggestions {
  padding: 12px 20px;
  background: rgba(255, 255, 255, 0.6);
  border-top: 1px solid rgba(229, 230, 235, 0.5);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestion-chip {
  padding: 6px 12px;
  background: rgba(30, 58, 138, 0.08);
  border: 1px solid rgba(30, 58, 138, 0.15);
  border-radius: 16px;
  font-size: 13px;
  color: #1e3a8a;
  cursor: pointer;
  transition: all 0.2s ease;
}

.suggestion-chip:hover {
  background: rgba(30, 58, 138, 0.15);
  border-color: rgba(30, 58, 138, 0.25);
  transform: translateY(-1px);
}

/* ---------------------------------------------------------------------------
   输入区
   --------------------------------------------------------------------------- */
.copilot-footer {
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(229, 230, 235, 0.5);
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.copilot-footer :deep(.el-textarea__inner) {
  border-radius: 12px;
  resize: none;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(229, 230, 235, 0.5);
}

.copilot-footer :deep(.el-textarea__inner:focus) {
  border-color: #1e3a8a;
}

.input-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.input-toolbar .el-button {
  height: 40px;
  width: 40px;
  border-radius: 10px;
  padding: 0;
  font-weight: 600;
  background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
  border: none;
}

.copilot-footer .el-button:hover {
  background: linear-gradient(135deg, #2563eb 0%, #60a5fa 100%);
}

.copilot-model-bar {
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.6);
  border-bottom: 1px solid rgba(229, 230, 235, 0.5);
}

/* 连通性状态条 */
.connectivity-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  font-size: 12px;
  font-weight: 500;
  border-bottom: 1px solid rgba(229, 230, 235, 0.5);
}

.connectivity-bar.error {
  background: #fef2f2;
  color: #dc2626;
}

.connectivity-bar .el-icon {
  font-size: 14px;
}
</style>