<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import {
  DataAnalysis,
  DocumentChecked,
  TrendCharts,
  OfficeBuilding,
  List,
  Setting,
  Fold,
  Expand,
  SwitchButton,
} from '@element-plus/icons-vue'
import AppHeader from '@/components/AppHeader.vue'
import CompareProgress from '@/components/CompareProgress.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import { useCompareStore } from '@/store/compare'
import { useUserStore } from '@/store'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

type MenuKey = 'dashboard' | 'compare' | 'tasks' | 'review' | 'personal' | 'audit' | 'admin'

const props = defineProps<{
  activeMenu: MenuKey
  isAdmin?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:activeMenu', val: MenuKey): void
  (e: 'menuSelect', index: string): void
}>()

const compareStore = useCompareStore()
const userStore = useUserStore()
const router = useRouter()

const resolvedIsAdmin = computed(() => props.isAdmin ?? userStore.isAdmin)

const onMenuSelect = (index: string) => {
  emit('update:activeMenu', index as MenuKey)
  emit('menuSelect', index)
}

const handleLogout = () => {
  userStore.clearAuth()
  ElMessage.success('已退出登录')
  router.push('/login')
}

// ------------------------------------------------------------------
// 移动端响应式：侧边栏折叠
// ------------------------------------------------------------------
const MOBILE_BREAKPOINT = 768
const isMobile = ref(false)
const sidebarCollapsed = ref(true)

const checkMobile = () => {
  isMobile.value = window.innerWidth <= MOBILE_BREAKPOINT
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const handleMenuClick = (index: string) => {
  onMenuSelect(index)
  if (isMobile.value) {
    sidebarCollapsed.value = true
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<template>
  <div class="app-container">
    <!-- 全局顶部导航栏 -->
    <AppHeader />

    <!-- 移动端汉堡菜单按钮 -->
    <div v-if="isMobile" class="mobile-menu-toggle" @click="toggleSidebar">
      <el-icon :size="20">
        <Expand v-if="sidebarCollapsed" />
        <Fold v-else />
      </el-icon>
    </div>

    <!-- 移动端侧边栏遮罩 -->
    <div
      v-if="isMobile && !sidebarCollapsed"
      class="mobile-sidebar-overlay"
      @click="sidebarCollapsed = true"
    />

    <el-container class="main-layout">
      <!-- 左侧边栏菜单 -->
      <el-aside
        :width="isMobile ? '200px' : '220px'"
        class="side-menu"
        :class="{ 'mobile-collapsed': isMobile && sidebarCollapsed }"
      >
        <el-menu
          :default-active="activeMenu"
          class="home-menu"
          @select="handleMenuClick"
        >
          <el-menu-item index="dashboard">
            <el-icon><DataAnalysis /></el-icon>
            <span>数据驾驶舱</span>
          </el-menu-item>

          <el-menu-item v-if="!userStore.isGuest" index="compare">
            <el-icon><DocumentChecked /></el-icon>
            <span>智能比对</span>
          </el-menu-item>

          <el-menu-item index="tasks">
            <el-icon><List /></el-icon>
            <span>任务中心</span>
            <el-badge
              v-if="compareStore.activeTasks.length > 0"
              :value="compareStore.activeTasks.length"
              class="menu-badge"
            />
          </el-menu-item>

          <el-menu-item index="personal">
            <el-icon><TrendCharts /></el-icon>
            <span>我的比对记录</span>
          </el-menu-item>

          <el-menu-item v-if="userStore.isAdmin && !userStore.isGuest" index="audit">
            <el-icon><OfficeBuilding /></el-icon>
            <span>公司审计档案</span>
          </el-menu-item>

          <el-menu-item v-if="userStore.isAdmin && !userStore.isGuest" index="admin">
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </el-menu-item>
        </el-menu>

        <!-- 手机端：侧边栏底部退出登录 -->
        <div v-if="isMobile" class="mobile-logout">
          <el-divider />
          <el-button type="danger" text @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            <span>{{ userStore.isGuest ? '退出' : '退出登录' }}</span>
          </el-button>
        </div>
      </el-aside>

      <!-- 右侧主内容区 -->
      <el-main class="main-content-wrapper">
        <slot />
      </el-main>
    </el-container>

    <!-- 进度弹窗 -->
    <CompareProgress
      :visible="compareStore.progressVisible"
      :percent="compareStore.progressPercent"
      :status="compareStore.progressStatus"
      :process-mode="compareStore.progressProcessMode"
      :is-cancelling="compareStore.isCancelling"
      @cancel="compareStore.cancelCurrentTask"
      @minimize="compareStore.hideTaskProgress(compareStore.currentViewTaskId)"
    />

    <!-- AI 智能助手 -->
    <AIAssistant :task-id="compareStore.currentTaskId" />
  </div>
</template>

<style scoped>
.app-container {
  min-height: 100vh;
  background: #f7f8fa;
}

.main-layout {
  max-width: 1600px;
  margin: 0 auto;
  min-height: calc(100vh - 64px);
}

.side-menu {
  background: #ffffff;
  border-right: 1px solid #f0f2f5;
  padding-top: 12px;
}

.home-menu {
  border-right: none;
  background: transparent;
}

.home-menu :deep(.el-menu-item) {
  font-size: 14px;
  letter-spacing: 0.3px;
  color: #4e5969;
  height: 48px;
  line-height: 48px;
  margin: 4px 12px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.home-menu :deep(.el-menu-item:hover) {
  color: #1d2129;
  background: rgba(24, 144, 255, 0.04);
}

.home-menu :deep(.el-menu-item.is-active) {
  color: #1e3a8a;
  font-weight: 600;
  background: rgba(24, 144, 255, 0.05);
  position: relative;
}

.home-menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: #1e3a8a;
  border-radius: 0 2px 2px 0;
}

.home-menu :deep(.el-menu-item .el-icon) {
  color: #86909c;
  font-size: 18px;
  margin-right: 8px;
}

.home-menu :deep(.el-menu-item:hover .el-icon) {
  color: #4e5969;
}

.home-menu :deep(.el-menu-item.is-active .el-icon) {
  color: #1e3a8a;
}

.main-content-wrapper {
  padding: 20px 24px 40px;
  background: #f7f8fa;
}

.menu-badge {
  margin-left: auto;
  margin-right: 4px;
}

.menu-badge :deep(.el-badge__content) {
  border: none;
  font-size: 11px;
  height: 16px;
  line-height: 16px;
  padding: 0 5px;
}

/* ============================================================================
   移动端响应式样式
   ============================================================================ */

@media (max-width: 768px) {
  .main-layout {
    max-width: 100vw;
    margin: 0;
    min-height: calc(100vh - 56px);
    position: relative;
  }

  .mobile-menu-toggle {
    position: fixed;
    top: 72px;
    left: 12px;
    z-index: 1001;
    width: 36px;
    height: 36px;
    background: #ffffff;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    cursor: pointer;
    color: #1e3a8a;
  }

  .mobile-sidebar-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 998;
  }

  .side-menu {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    z-index: 999;
    transition: transform 0.3s ease;
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
    padding-top: 56px;
  }

  .side-menu.mobile-collapsed {
    transform: translateX(-100%);
  }

  .main-content-wrapper {
    padding: 12px 12px 24px;
    min-width: 0;
  }

  :deep(.el-container) {
    display: block !important;
  }

  :deep(.el-main) {
    padding: 0;
    overflow-x: hidden;
  }

  /* 手机端侧边栏底部退出登录 */
  .mobile-logout {
    padding: 8px 16px 20px;
  }

  .mobile-logout .el-button {
    width: 100%;
    justify-content: flex-start;
    font-size: 14px;
    color: #ef4444;
  }

  .mobile-logout .el-button:hover {
    color: #dc2626;
    background: #fef2f2;
  }

  .mobile-logout .el-icon {
    margin-right: 8px;
    font-size: 18px;
  }
}

/* ============================================================================
   打印专用样式
   ============================================================================ */
@media print {
  /* 隐藏侧边栏 */
  .side-menu {
    display: none !important;
  }

  /* 隐藏顶部导航 */
  :deep(.app-header),
  :deep(.app-header *) {
    display: none !important;
  }

  /* 主内容区占满宽度 */
  .main-layout {
    max-width: 100% !important;
    margin: 0 !important;
    display: block !important;
  }

  /* 确保 el-container 在打印时正确显示 */
  :deep(.el-container) {
    display: block !important;
  }

  .main-content-wrapper {
    padding: 0 !important;
    background: #ffffff !important;
    display: block !important;
    overflow: visible !important;
    height: auto !important;
    min-height: auto !important;
  }

  /* 确保 el-main 正确显示 */
  :deep(.el-main) {
    overflow: visible !important;
    padding: 0 !important;
  }

  /* 确保 Dashboard 在打印时显示，其他视图隐藏 */
  :deep(.dashboard-view) {
    display: block !important;
    height: auto !important;
    overflow: visible !important;
  }

  :deep(.compare-view),
  :deep(.records-view),
  :deep(.audit-view) {
    display: none !important;
  }

  /* 隐藏 AI 助手 - 选择固定定位的元素 */
  :deep([class*="ai-assistant"]) {
    display: none !important;
  }

  /* 隐藏进度弹窗 */
  :deep(.compare-progress) {
    display: none !important;
  }
}
</style>
