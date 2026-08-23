<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  User,
  Lock,
  Postcard,
  OfficeBuilding,
  UserFilled,
  DocumentCopy,
  CircleCheckFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import api from '@/api'
import { useUserStore } from '@/store'

const router = useRouter()
const userStore = useUserStore()
const isLogin = ref(true)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  username: '',
  password: '',
  full_name: '',
  employee_id: '',
  position: '',
})

const contactDialogVisible = ref(false)
const guideDialogVisible = ref(false)

const teamMembers = [
  { name: '杨柏林', role: '队长 / 产品负责人', affiliation: '中山大学' },
  { name: '周璐', role: '技术研发负责人', affiliation: '中山大学' },
  { name: '石现', role: '商业与财务负责人', affiliation: '中山大学' },
  { name: '玉智豪', role: '银行合规业务专家', affiliation: '中山大学' },
  { name: '李庆', role: '全栈开发与交互负责人', affiliation: '中山大学' },
]

const handleLogin = async () => {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('username', loginForm.username)
    params.append('password', loginForm.password)
    const res = await api.post('/api/v1/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    const { access_token } = res.data
    userStore.setToken(access_token)
    await userStore.fetchUserInfo()
    ElMessage.success('登录成功')
    router.push('/')
  } catch (err: any) {
    const msg = err.response?.data?.detail || '登录失败，请检查网络或账号密码'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

const handleGuestLogin = async () => {
  loading.value = true
  try {
    const res = await api.post('/api/v1/auth/guest')
    const { access_token } = res.data
    userStore.setGuestToken(access_token)
    ElMessage.success('游客登录成功')
    router.push('/')
  } catch (err: any) {
    const msg = err.response?.data?.detail || '游客登录失败，请稍后重试'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!registerForm.username || !registerForm.password) {
    ElMessage.warning('用户名和密码为必填项')
    return
  }
  loading.value = true
  try {
    await api.post('/api/v1/auth/register', {
      username: registerForm.username,
      password: registerForm.password,
      full_name: registerForm.full_name,
      employee_id: registerForm.employee_id,
      position: registerForm.position,
    })
    ElMessage.success('提交成功，等待管理员审核')
    isLogin.value = true
    loginForm.username = registerForm.username
    loginForm.password = ''
  } catch (err: any) {
    const msg = err.response?.data?.detail || '注册失败，请稍后重试'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- 全局背景层 -->
    <div class="bg-layer" />

    <!-- 顶部导航栏 -->
    <nav class="top-nav">
      <div class="nav-left">
        <img src="/logo.png" alt="logo" class="nav-logo" />
        <span class="nav-brand">智契 SMARTPACT</span>
      </div>
      <div class="nav-right">
        <button class="nav-link" @click="guideDialogVisible = true">操作指南</button>
        <button class="nav-link" @click="contactDialogVisible = true">联系开发者</button>
      </div>
    </nav>

    <!-- 主体内容区 -->
    <div class="main-container">
      <!-- 左侧品牌与特性 -->
      <div class="brand-section">
        <div class="brand-header">
          <div class="brand-titles">
            <h1 class="brand-title">智契 SMARTPACT</h1>
            <p class="brand-subtitle">新一代企业级 AI 风控基础设施</p>
          </div>
        </div>

        <div class="features-list">
          <div class="feature-item">
            <div class="feature-icon-wrap">
              <el-icon class="feature-icon" :size="22"><DocumentCopy /></el-icon>
            </div>
            <div class="feature-text">
              <div class="feature-label">智能文档比对</div>
              <div class="feature-desc">多agent协同深度解析</div>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon-wrap">
              <el-icon class="feature-icon" :size="22"><CircleCheckFilled /></el-icon>
            </div>
            <div class="feature-text">
              <div class="feature-label">合规自动审查</div>
              <div class="feature-desc">法务级风险识别与整改</div>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon-wrap">
              <el-icon class="feature-icon" :size="22"><WarningFilled /></el-icon>
            </div>
            <div class="feature-text">
              <div class="feature-label">实时风险预警</div>
              <div class="feature-desc">数据交叉验证与风险定级</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧登录玻璃卡片 -->
      <div class="login-card-wrapper">
        <div class="login-card">
          <div class="card-header">
            <h2 class="card-title">{{ isLogin ? '欢迎登录' : '注册账号' }}</h2>
            <p class="card-subtitle">
              {{ isLogin ? '请使用您的账号密码安全登录系统' : '填写信息提交注册申请' }}
            </p>
          </div>

          <div class="card-body">
            <template v-if="isLogin">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入账号"
                :prefix-icon="User"
                size="large"
                class="glass-input"
                @keyup.enter="handleLogin"
              />
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                size="large"
                show-password
                class="glass-input"
                @keyup.enter="handleLogin"
              />
              <el-button
                type="primary"
                size="large"
                class="login-btn"
                :loading="loading"
                @click="handleLogin"
              >
                安全登录
              </el-button>
              <el-divider class="guest-divider">
                <span class="divider-text">或</span>
              </el-divider>
              <el-button
                size="large"
                class="guest-btn"
                :loading="loading"
                @click="handleGuestLogin"
              >
                <el-icon><User /></el-icon>
                游客访问
              </el-button>
              <p class="guest-hint">
                无需注册，可查看数据驾驶舱、最近5条比对记录及使用智契 Copilot
              </p>
            </template>

            <template v-else>
              <el-input
                v-model="registerForm.username"
                placeholder="请输入用户名"
                :prefix-icon="User"
                size="large"
                class="glass-input"
              />
              <el-input
                v-model="registerForm.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                size="large"
                show-password
                class="glass-input"
              />
              <el-input
                v-model="registerForm.full_name"
                placeholder="请输入真实姓名"
                :prefix-icon="UserFilled"
                size="large"
                class="glass-input"
              />
              <el-input
                v-model="registerForm.employee_id"
                placeholder="请输入工号"
                :prefix-icon="Postcard"
                size="large"
                class="glass-input"
              />
              <el-input
                v-model="registerForm.position"
                placeholder="请输入职务"
                :prefix-icon="OfficeBuilding"
                size="large"
                class="glass-input"
              />
              <el-button
                type="primary"
                size="large"
                class="login-btn"
                :loading="loading"
                @click="handleRegister"
              >
                提交注册
              </el-button>
            </template>
          </div>

          <div class="card-footer">
            <span class="toggle-link" @click="isLogin = !isLogin">
              {{ isLogin ? '还没有账号？立即注册' : '已有账号？返回登录' }}
            </span>
          </div>
        </div>
      </div>

      <!-- 版权信息 -->
      <div class="brand-footer">
        <span class="footer-text">© 2026 智契 SMARTPACT. 保留所有权利。</span>
      </div>
    </div>

    <!-- 联系开发者 Dialog -->
    <el-dialog
      v-model="contactDialogVisible"
      title="联系开发团队"
      width="560px"
      align-center
      :close-on-click-modal="true"
    >
      <el-table :data="teamMembers" border stripe size="small" style="width: 100%">
        <el-table-column prop="name" label="姓名" width="90" align="center" />
        <el-table-column prop="role" label="团队角色" min-width="160" />
        <el-table-column prop="affiliation" label="所属单位" width="120" align="center" />
      </el-table>
      <div style="margin-top: 16px; font-size: 13px; color: #64748b; line-height: 1.8">
        <p><strong>产品负责人：</strong>杨柏林 &nbsp;|&nbsp; 电话：18725169837 &nbsp;|&nbsp; 邮箱：2863846826@qq.com</p>
        <p><strong>团队地址：</strong>中山大学珠海校区 · 海琴一号</p>
      </div>
    </el-dialog>

    <!-- 平台操作指南 Dialog -->
    <el-dialog
      v-model="guideDialogVisible"
      title="智契 AI 平台操作指南"
      width="640px"
      align-center
      :close-on-click-modal="true"
    >
      <div class="guide-content">
        <div class="guide-section">
          <h3>1. 文档上传与批量比对</h3>
          <p>
            支持上传 <strong>采购结果公告</strong> 与 <strong>合同文本</strong> 进行智能比对，兼容 PDF、Word、TXT 格式。
            可一次上传多组文件，系统支持 <strong>智能配对</strong> 与 <strong>批量队列比对</strong>，并可通过并发控制器调节同时处理任务数（1-5），兼顾效率与稳定性。
          </p>
        </div>
        <div class="guide-section">
          <h3>2. 任务中心与后台运行</h3>
          <p>
            提交比对后任务进入 <strong>后台队列</strong>，可在「任务中心」实时查看多任务进度、取消或重试失败任务。
            任务完成后自动推送桌面通知，页面刷新后亦能恢复未完成的任务并继续轮询。
          </p>
        </div>
        <div class="guide-section">
          <h3>3. RAG 深度检索与视觉溯源</h3>
          <p>
            长文档自动触发 <strong>RAG 深度检索引擎</strong>，基于向量语义检索实现细粒度比对。
            比对结果中支持 <strong>视觉溯源</strong>：点击风险点可直接定位到合同 PDF 原文对应位置，实现风险条款的精准复核。
          </p>
        </div>
        <div class="guide-section">
          <h3>4. 智契 Copilot AI 助手</h3>
          <p>
            点击右下角悬浮图标唤醒 <strong>智契 Copilot</strong>，支持合同解读、风险分析、整改建议等交互问答。
            系统支持多模型动态切换，可在 Copilot 内选择不同底层大模型进行对话。
          </p>
        </div>
        <div class="guide-section">
          <h3>5. 模型管理与动态切换</h3>
          <p>
            管理员可在「系统管理 → 模型管理」中配置多个大模型（DeepSeek、Moonshot、通义千问、智谱等），
            支持 <strong>显示名称</strong> 与 <strong>API 模型 ID</strong> 分离，避免模型名称与接口 ID 不一致导致的调用失败。
          </p>
        </div>
        <div class="guide-section">
          <h3>6. 智能整改函生成</h3>
          <p>
            在比对结果页点击 <strong>「AI 生成官方整改告知函」</strong>，系统将根据识别的风险点自动生成标准化整改函草稿，支持在线预览与一键导出。
          </p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif;
}

/* ===== 全局背景图 ===== */
.bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: url('/login-bg.jpg') no-repeat center center;
  background-size: cover;
  background-position: center;
}

.bg-layer::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(240, 247, 255, 0.2) 0%, rgba(219, 234, 254, 0.15) 100%);
  pointer-events: none;
}

/* ===== 顶部导航栏 ===== */
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 48px;
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(12px) saturate(160%);
  -webkit-backdrop-filter: blur(12px) saturate(160%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.5);
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-logo {
  height: 44px;
  width: auto;
  object-fit: contain;
}

.nav-brand {
  font-size: 19px;
  font-weight: 800;
  color: #1e3a8a;
  letter-spacing: 1.5px;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 28px;
}

.nav-link {
  background: none;
  border: none;
  color: #475569;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 0;
  transition: all 0.25s ease;
  letter-spacing: 0.5px;
  position: relative;
}

.nav-link::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  width: 0;
  height: 1.5px;
  background: linear-gradient(90deg, transparent, #2563eb, transparent);
  transition: all 0.3s ease;
  transform: translateX(-50%);
}

.nav-link:hover {
  color: #2563eb;
}

.nav-link:hover::after {
  width: 100%;
}

/* ===== 主体内容区 ===== */
.main-container {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  padding: 80px 8% 40px;
  box-sizing: border-box;
}

/* ===== 左侧品牌区 ===== */
 .brand-section {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
  gap: 48px;
  flex: 1;
  max-width: 560px;
  padding-left: 10%;
  padding-top: 8vh;
  animation: fadeInLeft 0.8s ease-out;
}

@keyframes fadeInLeft {
  from {
    opacity: 0;
    transform: translateX(-40px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.brand-header {
  display: flex;
  align-items: center;
}

.brand-titles {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

 .brand-title {
  margin: 0;
  font-size: 60px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: 3px;
  line-height: 1.2;
}

.brand-subtitle {
  margin: 0;
  font-size: 20px;
  color: #64748b;
  font-weight: 400;
  letter-spacing: 2px;
}

/* ===== 特性列表 ===== */
.features-list {
  display: flex;
  flex-direction: row;
  gap: 40px;
  margin-top: 8px;
}

.feature-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 0;
  background: transparent;
  border: none;
  transition: all 0.3s ease;
}

.feature-item:hover {
  transform: translateY(-4px);
}

.feature-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow:
    0 4px 12px rgba(37, 99, 235, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(191, 219, 254, 0.6);
  transition: all 0.4s ease;
}

.feature-item:hover .feature-icon-wrap {
  transform: scale(1.08);
  box-shadow:
    0 6px 20px rgba(37, 99, 235, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
}

.feature-icon {
  color: #2563eb;
  font-size: 24px;
}

.feature-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.feature-label {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  letter-spacing: 0.5px;
}

.feature-desc {
  font-size: 12px;
  color: #64748b;
}

/* ===== 品牌底部 ===== */
.brand-footer {
  position: absolute;
  bottom: 24px;
  left: 48px;
}

.footer-text {
  font-size: 14px;
  color: #94a3b8;
  letter-spacing: 0.5px;
}

/* ===== 右侧登录卡片 ===== */
.login-card-wrapper {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: 1;
  animation: fadeInRight 0.8s ease-out;
  position: relative;
}

/* 卡片环境光晕 */
.login-card-wrapper::before {
  content: '';
  position: absolute;
  width: 480px;
  height: 600px;
  background: radial-gradient(ellipse, rgba(37, 99, 235, 0.06) 0%, transparent 70%);
  pointer-events: none;
  z-index: -1;
}

@keyframes fadeInRight {
  from {
    opacity: 0;
    transform: translateX(40px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

 .login-card {
  width: 420px;
  padding: 44px 40px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 16px;
  box-shadow:
    0 8px 32px rgba(30, 58, 138, 0.08),
    0 2px 8px rgba(0, 0, 0, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  position: relative;
  overflow: hidden;
}

/* 卡片顶部微妙高光 */
.login-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 1), transparent);
}

.card-header {
  margin-bottom: 24px;
}

.card-title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  color: #1e3a8a;
  letter-spacing: 1.5px;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.card-subtitle {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  letter-spacing: 0.5px;
  line-height: 1.5;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* ===== 玻璃输入框 ===== */
.glass-input :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.8) !important;
  box-shadow: none !important;
  border: 1px solid rgba(255, 255, 255, 0.6) !important;
  border-radius: 10px !important;
  padding: 0 14px !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.glass-input :deep(.el-input__wrapper:hover) {
  border-color: rgba(37, 99, 235, 0.5) !important;
  background: rgba(255, 255, 255, 0.95) !important;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08) !important;
}

.glass-input :deep(.el-input__wrapper.is-focus) {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15), 0 2px 12px rgba(37, 99, 235, 0.1) !important;
  background: #ffffff !important;
}

.glass-input :deep(.el-input__inner) {
  color: #1e293b;
  font-size: 15px;
  height: 42px;
}

.glass-input :deep(.el-input__inner::placeholder) {
  color: #94a3b8;
  font-size: 14px;
}

.glass-input :deep(.el-input__icon) {
  color: #2563eb;
  font-size: 16px;
}

/* ===== 渐变登录按钮 ===== */
.login-btn {
  width: 100%;
  height: 46px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #fff;
  background: linear-gradient(135deg, #2563eb 0%, #1e3a8a 100%);
  border: none;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(30, 58, 138, 0.3);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.login-btn:hover {
  box-shadow: 0 6px 24px rgba(30, 58, 138, 0.4);
  transform: translateY(-1px);
}

.login-btn::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.25), transparent);
  transform: skewX(-20deg);
  transition: left 0.6s ease;
}

.login-btn:hover::after {
  left: 150%;
}

/* ===== 底部切换链接 ===== */
.card-footer {
  text-align: center;
  margin-top: 20px;
}

.toggle-link {
  font-size: 13px;
  font-weight: 500;
  color: #2563eb;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  letter-spacing: 0.5px;
}

.toggle-link:hover {
  color: #1e40af;
  text-shadow: 0 0 8px rgba(37, 99, 235, 0.2);
}

/* ===== 游客访问按钮 ===== */
.guest-divider {
  margin: 4px 0;
}

.guest-divider :deep(.el-divider__text) {
  background: transparent;
  color: #94a3b8;
  font-size: 12px;
}

.guest-btn {
  width: 100%;
  height: 44px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #475569;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 10px;
  transition: all 0.3s ease;
}

.guest-btn:hover {
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(37, 99, 235, 0.4);
  color: #2563eb;
}

.guest-btn .el-icon {
  margin-right: 6px;
  font-size: 16px;
}

.guest-hint {
  text-align: center;
  font-size: 11px;
  color: #94a3b8;
  margin: 0;
  line-height: 1.5;
}

/* ===== Dialog 内容 ===== */
.guide-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.guide-section h3 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1e40af;
}

.guide-section p {
  margin: 0;
  font-size: 13px;
  color: #4e5969;
  line-height: 1.8;
}

.guide-section strong {
  color: #1d2129;
  font-weight: 600;
}

.guide-section strong {
  color: #1d2129;
  font-weight: 600;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 960px) {
  .top-nav {
    padding: 0 16px;
    height: 56px;
  }

  .nav-logo {
    height: 36px;
  }

  .nav-brand {
    font-size: 16px;
  }

  .nav-right {
    gap: 12px;
  }

  .nav-right .nav-link {
    font-size: 12px;
    letter-spacing: 0;
    padding: 2px 0;
  }

  .main-container {
    flex-direction: column;
    justify-content: flex-start;
    padding: 72px 16px 0;
    gap: 24px;
    height: 100vh;
    min-height: 100vh;
    box-sizing: border-box;
  }

  .brand-section {
    align-items: center;
    text-align: center;
    gap: 8px;
    padding-left: 0;
    padding-top: 2vh;
    max-width: 100%;
    flex-shrink: 0;
  }

  .brand-title {
    font-size: 28px;
    letter-spacing: 0.5px;
    line-height: 1.2;
    word-break: break-word;
  }

  .brand-subtitle {
    font-size: 13px;
    letter-spacing: 0.5px;
    line-height: 1.4;
  }

  .brand-header {
    flex-direction: column;
    gap: 4px;
  }

  .features-list {
    display: none;
  }

  .brand-footer {
    margin-top: 12px;
    padding: 8px 0 16px;
    text-align: center;
    flex-shrink: 0;
    position: relative;
    bottom: auto;
    left: auto;
  }

  .footer-text {
    font-size: 10px;
    color: #94a3b8;
  }

  .login-card-wrapper {
    justify-content: center;
    width: 100%;
    flex-shrink: 0;
  }

  .login-card-wrapper::before {
    display: none;
  }

  .login-card {
    width: 100%;
    max-width: 420px;
    padding: 28px 20px;
    border-radius: 12px;
  }

  .card-title {
    font-size: 22px;
  }

  .card-subtitle {
    font-size: 12px;
  }

  .glass-input :deep(.el-input__inner) {
    height: 40px;
    font-size: 14px;
  }

  .login-btn {
    height: 42px;
    font-size: 14px;
  }
}

@media (max-width: 480px) {
  .brand-title {
    font-size: 26px;
    letter-spacing: 0.5px;
  }

  .brand-subtitle {
    font-size: 12px;
  }

  .login-card {
    padding: 20px 16px;
    border-radius: 10px;
  }

  .card-title {
    font-size: 20px;
  }

  .glass-input :deep(.el-input__wrapper) {
    padding: 0 10px !important;
  }

  .glass-input :deep(.el-input__inner) {
    height: 38px;
  }

  .login-btn {
    height: 40px;
  }

  .card-body {
    gap: 14px;
  }

  .toggle-link {
    font-size: 12px;
  }
}
</style>
