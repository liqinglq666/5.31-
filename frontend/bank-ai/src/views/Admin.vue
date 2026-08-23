<script setup lang="ts">
/**
 * Admin.vue
 * ---------
 * 高管控制台（管理员视图）。
 * 使用 el-tabs 将页面划分为【待办审批】与【全量人员与审计】两大标签页。
 * 内部区块已拆分为独立子组件，Admin.vue 仅保留数据 orchestration 与业务逻辑。
 */

import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getPendingUsers,
  approveUser,
  getAllUsers,
  getUserRecords,
  toggleUserStatus,
  getAvailableModels,
} from '@/api'
import AppHeader from '@/components/AppHeader.vue'
import PendingApprovalTable from './Admin/components/PendingApprovalTable.vue'
import UserManagementTable from './Admin/components/UserManagementTable.vue'
import ModelManagementTable from './Admin/components/ModelManagementTable.vue'
import AuditTrailDrawer from './Admin/components/AuditTrailDrawer.vue'
import type { PendingUser, AdminUser, UserRecordItem } from './Admin/types'
import type { ModelItem } from '@/types/api'

// ---------------------------------------------------------------------------
// Tabs 状态
// ---------------------------------------------------------------------------
const activeTab = ref<'pending' | 'users' | 'models'>('pending')

// ---------------------------------------------------------------------------
// 待办审批页状态
// ---------------------------------------------------------------------------
const pendingUsers = ref<PendingUser[]>([])
const pendingLoading = ref(false)
const approvingId = ref<string | null>(null)

const fetchPendingUsers = async () => {
  pendingLoading.value = true
  try {
    const res = await getPendingUsers()
    pendingUsers.value = res.data.data || []
  } catch (_err) {
    ElMessage.error('获取待审批人员失败')
  } finally {
    pendingLoading.value = false
  }
}

const handleApprove = async (row: PendingUser) => {
  try {
    await ElMessageBox.confirm(
      `确认通过用户 "${row.username}" 的注册申请？`,
      '审批确认',
      { confirmButtonText: '通过', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  approvingId.value = row.id
  try {
    await approveUser(row.id)
    ElMessage.success(`已批准 ${row.username} 的注册申请`)
    await fetchPendingUsers()
  } catch (_err) {
    ElMessage.error('审批失败')
  } finally {
    approvingId.value = null
  }
}

// ---------------------------------------------------------------------------
// 全量人员与审计页状态
// ---------------------------------------------------------------------------
const allUsers = ref<AdminUser[]>([])
const usersLoading = ref(false)

const fetchAllUsers = async () => {
  usersLoading.value = true
  try {
    const res = await getAllUsers()
    allUsers.value = res.data.data || []
  } catch (_err) {
    ElMessage.error('获取人员列表失败')
  } finally {
    usersLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 审查轨迹抽屉状态
// ---------------------------------------------------------------------------
const drawerVisible = ref(false)
const drawerTitle = ref('合规审查轨迹')
const selectedUser = ref<AdminUser | null>(null)

const userRecords = ref<UserRecordItem[]>([])
const recordsLoading = ref(false)
const recordsPage = ref(1)
const recordsPageSize = ref(10)
const recordsTotal = ref(0)

const openAuditDrawer = async (user: AdminUser) => {
  selectedUser.value = user
  drawerTitle.value = `员工 ${user.full_name || user.username} 的合规审查轨迹`
  drawerVisible.value = true

  recordsPage.value = 1
  await loadUserRecords()
}

const loadUserRecords = async () => {
  if (!selectedUser.value) return
  recordsLoading.value = true
  try {
    const res = await getUserRecords(selectedUser.value.id, {
      page: recordsPage.value,
      page_size: recordsPageSize.value,
    })
    const payload = res.data.data
    userRecords.value = payload.list || []
    recordsTotal.value = payload.total || 0
    recordsPage.value = payload.page || 1
    recordsPageSize.value = payload.page_size || 10
  } catch (_err) {
    ElMessage.error('加载审查轨迹失败')
  } finally {
    recordsLoading.value = false
  }
}

const onRecordsPageChange = (page: number) => {
  recordsPage.value = page
  loadUserRecords()
}

const onRecordsSizeChange = (size: number) => {
  recordsPageSize.value = size
  recordsPage.value = 1
  loadUserRecords()
}

// ---------------------------------------------------------------------------
// 模型管理页状态
// ---------------------------------------------------------------------------
const models = ref<ModelItem[]>([])
const modelsLoading = ref(false)

const fetchModels = async () => {
  modelsLoading.value = true
  try {
    const res = await getAvailableModels()
    models.value = res.data.data || []
  } catch (_err) {
    ElMessage.error('获取模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 抽屉操作：导出审查记录 & 禁用/启用账号
// ---------------------------------------------------------------------------

const handleExportUserRecords = () => {
  if (!selectedUser.value || userRecords.value.length === 0) {
    ElMessage.warning('暂无可导出的审查记录')
    return
  }

  const headers = ['任务ID', '项目名称', '审查时间', '任务状态', '风险等级', '结论']
  const rows = userRecords.value.map((r) => [
    r.task_id,
    r.project_name,
    r.created_at || '',
    r.status,
    r.risk_level,
    r.conclusion,
  ])

  const escapeCsv = (cell: string) => {
    const str = String(cell || '')
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }
    return str
  }

  const csvContent = [headers, ...rows]
    .map((row) => row.map(escapeCsv).join(','))
    .join('\n')

  const blob = new Blob(['\ufeff' + csvContent], {
    type: 'text/csv;charset=utf-8;',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  const userName = selectedUser.value.full_name || selectedUser.value.username
  link.download = `${userName}_审查记录.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}

const handleToggleStatus = async (user: AdminUser) => {
  const actionText = user.status === 'active' ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确认${actionText}用户 "${user.username}" 的账号？`,
      '操作确认',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  try {
    const res = await toggleUserStatus(user.id)
    const newStatus = res.data.data.status
    user.status = newStatus
    const target = allUsers.value.find((u) => u.id === user.id)
    if (target) target.status = newStatus
    ElMessage.success(`已${newStatus === 'disabled' ? '禁用' : '启用'} ${user.username}`)
  } catch (_err) {
    ElMessage.error('操作失败')
  }
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------
onMounted(() => {
  fetchPendingUsers()
  fetchAllUsers()
  fetchModels()
})
</script>

<template>
  <div class="admin-page">
    <!-- 全局顶部导航栏 -->
    <AppHeader />

    <div class="admin-content">
      <el-tabs v-model="activeTab" type="border-card" class="admin-tabs">
        <!-- ============================= 待办审批 ============================= -->
        <el-tab-pane label="待办审批" name="pending">
          <PendingApprovalTable
            :users="pendingUsers"
            :loading="pendingLoading"
            :approving-id="approvingId"
            @refresh="fetchPendingUsers"
            @approve="handleApprove"
          />
        </el-tab-pane>

        <!-- ======================= 全量人员与审计 ======================= -->
        <el-tab-pane label="全量人员与审计" name="users">
          <UserManagementTable
            :users="allUsers"
            :loading="usersLoading"
            @refresh="fetchAllUsers"
            @view-audit="openAuditDrawer"
            @toggle-status="handleToggleStatus"
          />
        </el-tab-pane>

        <!-- ======================= 模型管理 ======================= -->
        <el-tab-pane label="模型管理" name="models">
          <ModelManagementTable
            :models="models"
            :loading="modelsLoading"
            @refresh="fetchModels"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- ======================= 审查轨迹抽屉 ======================= -->
    <AuditTrailDrawer
      v-model="drawerVisible"
      :title="drawerTitle"
      :user="selectedUser"
      :records="userRecords"
      :loading="recordsLoading"
      :page="recordsPage"
      :page-size="recordsPageSize"
      :total="recordsTotal"
      @update:page="onRecordsPageChange"
      @update:page-size="onRecordsSizeChange"
      @export="handleExportUserRecords"
      @toggle-status="handleToggleStatus"
    />
  </div>
</template>

<style>
.admin-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #f0f5ff 0%, #ffffff 100%);
  padding-bottom: 40px;
}

.admin-content {
  max-width: 1400px;
  margin: 24px auto 0;
  padding: 0 24px;
}

/* Tabs 容器 */
.admin-tabs .el-tabs__header {
  margin-bottom: 0;
}

.admin-tabs .el-tabs__content {
  padding: 0;
}
</style>
