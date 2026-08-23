<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'
import type { PendingUser } from '../types'

const props = defineProps<{
  users: PendingUser[]
  loading: boolean
  approvingId: string | null
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'approve', user: PendingUser): void
}>()
</script>

<template>
  <el-card shadow="hover" class="admin-card">
    <template #header>
      <div class="card-header">
        <span>待审批人员列表</span>
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
      <el-table-column prop="employee_id" label="工号" min-width="120">
        <template #default="{ row }">
          <span>{{ row.employee_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="position" label="职务" min-width="140">
        <template #default="{ row }">
          <span>{{ row.position || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="申请时间" min-width="170" />
      <el-table-column label="操作" width="140" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            type="success"
            size="small"
            :icon="Check"
            :loading="approvingId === row.id"
            @click="emit('approve', row)"
          >
            通过审核
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty
      v-if="!loading && props.users.length === 0"
      description="暂无待审批人员"
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
