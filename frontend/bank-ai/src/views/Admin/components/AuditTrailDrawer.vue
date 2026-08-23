<script setup lang="ts">
import { computed } from 'vue'
import { OfficeBuilding, Clock, Download } from '@element-plus/icons-vue'
import { riskLevelTag } from '@/utils/risk'
import type { AdminUser, UserRecordItem } from '../types'

const props = defineProps<{
  modelValue: boolean
  title: string
  user: AdminUser | null
  records: UserRecordItem[]
  loading: boolean
  page: number
  pageSize: number
  total: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:page', page: number): void
  (e: 'update:pageSize', size: number): void
  (e: 'export'): void
  (e: 'toggle-status', user: AdminUser): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const currentPage = computed({
  get: () => props.page,
  set: (val) => emit('update:page', val),
})

const currentPageSize = computed({
  get: () => props.pageSize,
  set: (val) => emit('update:pageSize', val),
})
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="title"
    size="680px"
    destroy-on-close
  >
    <div v-loading="loading" class="drawer-body">
      <!-- 员工简要信息条 -->
      <div v-if="user" class="user-info-bar">
        <div class="info-left">
          <el-icon><OfficeBuilding /></el-icon>
          <span class="info-item">
            <strong>{{ user.full_name || user.username }}</strong>
          </span>
          <span v-if="user.employee_id" class="info-item">
            工号：{{ user.employee_id }}
          </span>
          <span v-if="user.position" class="info-item">
            职务：{{ user.position }}
          </span>
        </div>
        <div class="info-actions">
          <el-button
            type="primary"
            size="small"
            :icon="Download"
            @click="emit('export')"
          >
            导出审查记录
          </el-button>
          <el-button
            v-if="user.status !== 'pending'"
            :type="user.status === 'active' ? 'danger' : 'success'"
            size="small"
            @click="emit('toggle-status', user)"
          >
            {{ user.status === 'active' ? '禁用账号' : '启用账号' }}
          </el-button>
        </div>
      </div>

      <!-- 时间轴展示审查记录 -->
      <el-timeline v-if="records.length > 0">
        <el-timeline-item
          v-for="(item, index) in records"
          :key="item.task_id"
          :icon="Clock"
          :type="riskLevelTag(item.risk_level).type || 'primary'"
          :timestamp="item.created_at || ''"
          placement="top"
        >
          <el-card shadow="hover" class="timeline-card">
            <template #header>
              <div class="timeline-header">
                <span class="project-name">{{ item.project_name }}</span>
                <el-tag
                  :type="riskLevelTag(item.risk_level).type"
                  size="small"
                  effect="dark"
                >
                  {{ riskLevelTag(item.risk_level).text }}
                </el-tag>
              </div>
            </template>
            <div class="timeline-body">
              <div class="timeline-row">
                <span class="label">结论：</span>
                <span class="value">{{ item.conclusion || '暂无结论' }}</span>
              </div>
              <div class="timeline-row">
                <span class="label">任务状态：</span>
                <span class="value">{{ item.status }}</span>
              </div>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else description="该员工暂无任何审查记录" />

      <!-- 分页器 -->
      <div v-if="total > 0" class="records-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="currentPageSize"
          :page-sizes="[5, 10, 20, 50]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="(p: number) => emit('update:page', p)"
          @size-change="(s: number) => emit('update:pageSize', s)"
        />
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  padding: 0 8px 24px;
}

.user-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 20px;
  color: #1e40af;
  font-size: 14px;
}

.user-info-bar .info-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.user-info-bar .info-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-info-bar .info-item {
  white-space: nowrap;
}

.timeline-card {
  border-radius: 10px;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #1e3a8a;
}

.project-name {
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #475569;
}

.timeline-row {
  display: flex;
}

.timeline-row .label {
  flex-shrink: 0;
  width: 72px;
  color: #64748b;
}

.timeline-row .value {
  flex: 1;
  line-height: 1.5;
}

.records-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}
</style>
