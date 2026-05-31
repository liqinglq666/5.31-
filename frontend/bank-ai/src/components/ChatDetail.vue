<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, ChatDotRound, Search } from '@element-plus/icons-vue'
import VueMarkdown from 'vue-markdown-render'
import api from '@/api'
import { TOKEN_KEY } from '@/utils/constants'
import { useModelStore } from '@/store'
import ModelSelector from '@/components/ModelSelector.vue'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const modelStore = useModelStore()

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
// 初始化欢迎消息
// ---------------------------------------------------------------------------
onMounted(() => {
  if (messages.value.length === 0) {
    messages.value = [
      {
        role: 'assistant',
        content:
          '**您好！我是智契 Copilot。**\n\n' +
          '我可以帮您解读合同风险、分析比对结果、生成整改建议。也可以针对已入库的合同进行跨文档语义检索（RAG）。有什么可以帮助您的吗？',
      },
    ]
  }
})

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

  messages.value.push({ role: 'user', content: text })
  inputMessage.value = ''
  isLoading.value = true
  isStreaming.value = false
  startThinkingTimer()
  await scrollToBottom()

  const history = messages.value.slice(-11, -1).map((m) => ({
    role: m.role,
    content: m.content,
  }))

  const aiMessage: ChatMessage = { role: 'assistant', content: '' }
  messages.value.push(aiMessage)

  const token = localStorage.getItem(TOKEN_KEY) || ''

  try {
    // 使用相对路径，让 Vite 代理自动转发到后端
    const endpoint = '/api/v1/chat/general'
    const body: any = { message: text, history, page_id: 'chat', search: enableSearch.value }
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
// RAG 语义检索
// ---------------------------------------------------------------------------
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const isSearching = ref(false)

const performRagSearch = async () => {
  const query = searchQuery.value.trim()
  if (!query) {
    ElMessage.warning('请输入检索关键词')
    return
  }
  isSearching.value = true
  searchResults.value = []
  try {
    const res = await api.post('/api/v1/memory/search', {
      query,
      top_k: 5,
    })
    if (res.data.code === 200) {
      searchResults.value = res.data.data || []
      if (searchResults.value.length === 0) {
        ElMessage.info('未检索到相关语义块')
      }
    } else {
      ElMessage.error(res.data.message || '检索失败')
    }
  } catch (_err) {
    ElMessage.error('检索请求失败，请检查 Milvus 服务是否正常运行')
  } finally {
    isSearching.value = false
  }
}

const activeTab = ref('chat')
</script>

<template>
  <div class="chat-detail-page">
    <!-- 左侧边栏：功能切换 -->
    <div class="chat-sidebar">
      <div class="sidebar-header">
        <div class="sidebar-icon">
          <img src="/ai-icon.png" alt="AI" />
        </div>
        <div class="sidebar-title">
          <span class="title-main">智契 Copilot</span>
          <span class="title-sub">AI 智能助手</span>
        </div>
      </div>

      <div class="sidebar-tabs">
        <div
          class="sidebar-tab"
          :class="{ active: activeTab === 'chat' }"
          @click="activeTab = 'chat'"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>智能对话</span>
        </div>
        <div
          class="sidebar-tab"
          :class="{ active: activeTab === 'rag' }"
          @click="activeTab = 'rag'"
        >
          <el-icon><Search /></el-icon>
          <span>语义检索</span>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="model-label">当前模型</div>
        <ModelSelector v-model="modelStore.currentModelId" size="small" />
      </div>
    </div>

    <!-- 右侧主内容区 -->
    <div class="chat-main">
      <!-- 智能对话面板 -->
      <div v-show="activeTab === 'chat'" class="chat-panel">
        <div ref="messagesContainerRef" class="chat-messages">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            class="message-row"
            :class="msg.role"
          >
            <div class="message-bubble">
              <div v-if="msg.role === 'assistant'" class="message-avatar">
                <img src="/ai-icon.png" alt="AI" />
              </div>
              <div class="message-content">
                <VueMarkdown v-if="msg.role === 'assistant'" :source="msg.content" />
                <template v-else>{{ msg.content }}</template>
              </div>
            </div>
          </div>

          <div v-if="isLoading && !isStreaming" class="message-row assistant">
            <div class="message-bubble">
              <div class="message-avatar">
                <img src="/ai-icon.png" alt="AI" />
              </div>
              <div class="thinking-indicator">
                <div class="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span class="thinking-text">正在思考中...（已思考{{ thinkingSeconds }}秒）</span>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-bar">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="2"
            placeholder="输入您的问题，按 Enter 发送..."
            resize="none"
            :disabled="isLoading"
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
              :disabled="!inputMessage.trim() || isLoading"
              @click="sendMessage"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <!-- RAG 语义检索面板 -->
      <div v-show="activeTab === 'rag'" class="rag-panel">
        <div class="rag-header">
          <h3>跨合同语义检索</h3>
          <p>基于 Milvus 向量数据库，检索已入库合同中的相关语义块</p>
        </div>

        <div class="rag-search-bar">
          <el-input
            v-model="searchQuery"
            placeholder="输入检索关键词，如：违约金条款、付款方式..."
            clearable
            @keydown.enter="performRagSearch"
          >
            <template #append>
              <el-button :loading="isSearching" @click="performRagSearch">
                检索
              </el-button>
            </template>
          </el-input>
        </div>

        <div v-if="isSearching" class="rag-loading">
          <el-skeleton :rows="5" animated />
        </div>

        <div v-else-if="searchResults.length > 0" class="rag-results">
          <div
            v-for="(item, idx) in searchResults"
            :key="idx"
            class="rag-result-card"
          >
            <div class="rag-result-header">
              <el-tag size="small" type="info">{{ item.level_1 || '未分类' }}</el-tag>
              <el-tag v-if="item.level_2" size="small" type="warning" style="margin-left: 8px">
                {{ item.level_2 }}
              </el-tag>
              <span class="rag-distance">相似度: {{ (item.distance * 100).toFixed(1) }}%</span>
            </div>
            <div class="rag-result-text">{{ item.text }}</div>
            <div class="rag-result-meta">
              <span>文档ID: {{ item.doc_id }}</span>
              <span>块ID: {{ item.chunk_id }}</span>
            </div>
          </div>
        </div>

        <div v-else-if="searchQuery && !isSearching" class="rag-empty">
          <el-empty description="暂无检索结果" />
        </div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.chat-detail-page {
  display: flex;
  height: 100vh;
  background: #f7f8fa;
}

/* ---------------------------------------------------------------------------
   左侧边栏
   --------------------------------------------------------------------------- */
.chat-sidebar {
  width: 260px;
  background: #ffffff;
  border-right: 1px solid #e5e6eb;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #f0f2f5;
}

.sidebar-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(30, 58, 138, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.sidebar-icon img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.sidebar-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title-main {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.title-sub {
  font-size: 12px;
  color: #86909c;
}

.sidebar-tabs {
  padding: 12px;
  flex: 1;
}

.sidebar-tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #4e5969;
  transition: all 0.2s ease;
  margin-bottom: 4px;
}

.sidebar-tab:hover {
  background: rgba(30, 58, 138, 0.04);
  color: #1d2129;
}

.sidebar-tab.active {
  background: rgba(30, 58, 138, 0.08);
  color: #1e3a8a;
  font-weight: 500;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid #f0f2f5;
}

.model-label {
  font-size: 12px;
  color: #86909c;
  margin-bottom: 8px;
}

/* ---------------------------------------------------------------------------
   右侧主内容区
   --------------------------------------------------------------------------- */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ---------------------------------------------------------------------------
   聊天面板
   --------------------------------------------------------------------------- */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-messages {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

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
  max-width: 75%;
  display: flex;
  gap: 12px;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.message-avatar img {
  width: 26px;
  height: 26px;
  object-fit: contain;
}

.message-content {
  padding: 14px 18px;
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
  background: #ffffff;
  color: #1d2129;
  border: 1px solid #e5e6eb;
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
  gap: 12px;
  padding: 14px 18px;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e5e6eb;
  border-bottom-left-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.thinking-text {
  font-size: 13px;
  color: #86909c;
  font-style: italic;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #86909c;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-indicator span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

/* 输入栏 */
.chat-input-bar {
  padding: 16px 32px;
  background: #ffffff;
  border-top: 1px solid #e5e6eb;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.chat-input-bar :deep(.el-textarea__inner) {
  border-radius: 12px;
  resize: none;
  font-size: 14px;
  background: #f7f8fa;
  border: 1px solid #e5e6eb;
}

.chat-input-bar :deep(.el-textarea__inner:focus) {
  border-color: #1e3a8a;
  background: #ffffff;
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
  flex-shrink: 0;
}

.input-toolbar .el-button:hover {
  background: linear-gradient(135deg, #2563eb 0%, #60a5fa 100%);
}

/* ---------------------------------------------------------------------------
   RAG 检索面板
   --------------------------------------------------------------------------- */
.rag-panel {
  padding: 24px 32px;
  overflow-y: auto;
  height: 100%;
}

.rag-header {
  margin-bottom: 20px;
}

.rag-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 6px;
}

.rag-header p {
  font-size: 13px;
  color: #86909c;
  margin: 0;
}

.rag-search-bar {
  margin-bottom: 24px;
  max-width: 600px;
}

.rag-loading {
  max-width: 800px;
}

.rag-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 900px;
}

.rag-result-card {
  background: #ffffff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
  transition: box-shadow 0.2s ease;
}

.rag-result-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.rag-result-header {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.rag-distance {
  margin-left: auto;
  font-size: 12px;
  color: #1e3a8a;
  font-weight: 500;
}

.rag-result-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1d2129;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f7f8fa;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 10px;
}

.rag-result-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #86909c;
}

.rag-empty {
  padding: 60px 0;
}
</style>