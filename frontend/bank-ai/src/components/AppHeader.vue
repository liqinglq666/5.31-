<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Setting, UserFilled, Timer, ArrowDown, Tools, Back, User } from '@element-plus/icons-vue'
import { useUserStore } from '@/store'
import { formatDateTime } from '@/utils/format'
import SystemSettingsDialog from '@/components/SystemSettingsDialog.vue'
import CurrentModelBadge from '@/components/CurrentModelBadge.vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const settingsVisible = ref(false)

// ---------------------------------------------------------------------------
// 实时时间
// ---------------------------------------------------------------------------
const currentTime = ref('')
let timeInterval: number | null = null

const updateTime = () => {
  currentTime.value = formatDateTime(new Date())
}

// ---------------------------------------------------------------------------
// 在线人数
// ---------------------------------------------------------------------------
const onlineCount = ref(0)
let onlineInterval: number | null = null

const fetchOnlineCount = async () => {
  try {
    const res = await api.get('/api/v1/system/online')
    if (res.data.code === 200) {
      onlineCount.value = res.data.data.count || 0
    }
  } catch (_err) {
    // 静默失败
  }
}

// ---------------------------------------------------------------------------
// 当前用户信息（来自全局 Store）
// ---------------------------------------------------------------------------
const userInfo = userStore.userInfo

const handleLogout = () => {
  userStore.clearAuth()
  router.push('/login')
}

onMounted(() => {
  updateTime()
  timeInterval = window.setInterval(updateTime, 1000)
  userStore.fetchUserInfo()

  fetchOnlineCount()
  onlineInterval = window.setInterval(fetchOnlineCount, 30000)
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
  if (onlineInterval) {
    clearInterval(onlineInterval)
  }
})
</script>

<template>
  <header class="system-header no-print">
    <div class="header-left">
      <el-button text class="back-btn mobile-only" @click="router.back()">
        <el-icon><Back /></el-icon>
      </el-button>
      <div class="brand-row">
        <img src="/logo.png" alt="logo" class="header-logo" />
        <span class="brand-text">智契 SMARTPACT</span>
      </div>
    </div>

    <div class="header-center">
      <div class="realtime-clock">
        <el-icon><Timer /></el-icon>
        <span>{{ currentTime }}</span>
      </div>
      <div class="online-badge">
        <el-icon><User /></el-icon>
        <span>{{ onlineCount }} 人在线</span>
      </div>
      <CurrentModelBadge />
    </div>

    <div class="header-right">
      <el-button v-if="!userStore.isGuest" text class="settings-btn" @click="settingsVisible = true">
        <el-icon><Tools /></el-icon>
        系统设置
      </el-button>

      <el-button
        v-if="userStore.isAdmin && !userStore.isGuest"
        text
        class="admin-btn"
        @click="router.push('/admin')"
      >
        <el-icon><Setting /></el-icon>
        管理员控制台
      </el-button>

      <el-dropdown trigger="hover" placement="bottom-end">
        <div class="user-trigger">
          <el-avatar :size="32" :icon="UserFilled" />
          <span class="user-name">{{ userStore.isGuest ? '游客' : (userInfo?.full_name || userInfo?.username || '用户') }}</span>
          <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <div class="user-card">
              <div class="user-card-row">
                <span class="label">姓名：</span>
                <span class="value">{{ userInfo?.full_name || '-' }}</span>
              </div>
              <div class="user-card-row">
                <span class="label">工号：</span>
                <span class="value">{{ userInfo?.employee_id || '-' }}</span>
              </div>
              <div class="user-card-row">
                <span class="label">职务：</span>
                <span class="value">{{ userInfo?.position || '-' }}</span>
              </div>
              <div class="user-card-row">
                <span class="label">部门：</span>
                <span class="value">合规审查部</span>
              </div>
              <el-divider style="margin: 10px 0" />
              <el-button type="danger" size="small" plain @click="handleLogout">
                {{ userStore.isGuest ? '退出' : '退出登录' }}
              </el-button>
            </div>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <SystemSettingsDialog v-model:visible="settingsVisible" />
  </header>
</template>

<style scoped>
.system-header {
  position: relative;
  background: #ffffff;
  color: #1d2129;
  height: 64px;
  padding: 0 24px;
  border-bottom: 1px solid #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
}

.header-left {
  flex: 1;
  display: flex;
  align-items: center;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-logo {
  height: 32px;
  width: auto;
  object-fit: contain;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  color: #1d2129;
  letter-spacing: 1px;
}

.header-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.realtime-clock {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #4e5969;
  background: #f7f8fa;
  padding: 6px 14px;
  border-radius: 20px;
  letter-spacing: 0.5px;
}

.realtime-clock .el-icon {
  color: #86909c;
}

.online-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #4e5969;
  background: #f0f9ff;
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid #bae6fd;
}

.online-badge .el-icon {
  color: #0284c7;
  font-size: 12px;
}

.header-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
}

.settings-btn,
.admin-btn {
  color: #4e5969;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.5px;
  transition: color 0.2s ease;
}

.settings-btn:hover,
.admin-btn:hover {
  color: #1e3a8a;
}

.settings-btn .el-icon,
.admin-btn .el-icon {
  margin-right: 4px;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.user-trigger:hover {
  background: #f7f8fa;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: #4e5969;
}

.dropdown-icon {
  font-size: 12px;
  color: #86909c;
}

.user-card {
  padding: 12px 16px;
  min-width: 180px;
}

.user-card-row {
  display: flex;
  align-items: center;
  font-size: 13px;
  margin-bottom: 6px;
}

.user-card-row .label {
  color: #86909c;
  width: 48px;
}

.user-card-row .value {
  color: #1d2129;
  font-weight: 500;
}

.back-btn {
  display: none;
}

.mobile-only {
  display: none;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 768px) {
  .system-header {
    height: 52px;
    padding: 0 10px;
  }

  .header-left {
    flex: 0 0 auto;
    min-width: 0;
  }

  .header-center {
    flex: 1;
    justify-content: flex-start;
    gap: 6px;
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
    padding: 0 4px;
  }

  .header-center::-webkit-scrollbar {
    display: none;
  }

  .header-right {
    flex: 0 0 auto;
    gap: 4px;
  }

  /* 手机端隐藏用户头像下拉菜单 */
  .header-right .el-dropdown {
    display: none;
  }

  .back-btn {
    display: inline-flex;
    padding: 4px;
    margin-right: 2px;
  }

  .mobile-only {
    display: inline-flex;
  }

  .header-logo {
    height: 26px;
  }

  .brand-text {
    font-size: 14px;
    letter-spacing: 0;
    white-space: nowrap;
  }

  .realtime-clock {
    font-size: 10px;
    padding: 3px 6px;
    gap: 3px;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .realtime-clock span {
    font-size: 10px;
    white-space: nowrap;
  }

  .online-badge {
    font-size: 9px;
    padding: 2px 5px;
    gap: 2px;
    flex-shrink: 0;
  }

  .online-badge .el-icon {
    font-size: 10px;
  }

  .online-badge span {
    display: none;
  }

  .settings-btn span,
  .admin-btn span {
    display: none;
  }

  .settings-btn .el-icon,
  .admin-btn .el-icon {
    margin-right: 0;
  }

  .user-name {
    display: none;
  }

  .dropdown-icon {
    display: none;
  }
}
</style>
