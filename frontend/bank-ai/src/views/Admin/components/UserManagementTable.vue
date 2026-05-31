<script setup lang="ts">
import { View } from '@element-plus/icons-vue'
import type { AdminUser } from '../types'

const props = defineProps<{
  users: AdminUser[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'view-audit', user: AdminUser): void
  (e: 'toggle-status', user: AdminUser): void
}>()

const statusText = (status?: string) => {
  const map: Record<string, string> = {
    pending: '待审批',
    active: '正常',
    disabled: '已禁用',
  }
  return map[status || ''] || status || '未知'
}

const statusType = (status?: string): any => {
  const map: Record<string, any> = {
    pending: 'warning',
    active: 'success',
    disabled: 'info',
  }
  return map[status || ''] || 'info'
}
</script>

<template>
  <el-card shadow="hover" class="admin-card">
    <template #header>
      <div class="card-header">
        <span>系统人员全览</span>
        <el-button type="primary" size="small" :loading="loading" @click="emit('refresh')">
          刷新
        </el-button>
      </div>
    </template>

    <el-table
      :data="props.users"
      border
      v-loading="loading"
      style="width: 100%"
    >
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="full_name" label="姓名" min-width="120">
        <template #default="{ row }">
          <span>{{ row.full_name || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="employee_id" label="工号" min-width="140">
        <template #default="{ row }">
          <span>{{ row.employee_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="position" label="职务" min-width="140">
        <template #default="{ row }">
          <span>{{ row.position || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="task_count" label="审查任务数" width="110" align="center">
        <template #default="{ row }">
          <span>{{ row.task_count ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="created_at"
        label="注册时间"
        min-width="170"
      />
      <el-table-column label="操作" width="150" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            :icon="View"
            @click="emit('view-audit', row)"
          >
            查看审查轨迹
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty
      v-if="!loading && props.users.length === 0"
      description="暂无人员数据"
    />
  </el-card>
</template>

<style scoped>
.admin-card {
  border-radius: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}
</style>
