<script setup lang="ts">
import { TrendCharts, Document, Warning, Timer } from '@element-plus/icons-vue'
import type { StatsData } from '@/types/api'
import { formatDuration } from '@/utils/format'

defineProps<{
  stats: StatsData
}>()
</script>

<template>
  <section class="stats-bar">
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-icon icon-blue">
            <el-icon :size="18"><TrendCharts /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_reviews }}</div>
            <div class="stat-label">累计审查总数</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-icon icon-primary">
            <el-icon :size="18"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.today_new }}</div>
            <div class="stat-label">今日新增</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-icon icon-red">
            <el-icon :size="18"><Warning /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value stat-risk">
              {{ (stats.high_risk_ratio * 100).toFixed(1) }}%
            </div>
            <div class="stat-label">高风险合同占比</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-icon icon-green">
            <el-icon :size="18"><Timer /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">
              {{ formatDuration(stats.avg_duration_seconds) }}
            </div>
            <div class="stat-label">平均比对耗时</div>
          </div>
        </div>
      </el-col>
    </el-row>
  </section>
</template>

<style scoped>
.stats-bar {
  max-width: 1400px;
  margin: 0 auto 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #ffffff;
  border-radius: 8px;
  padding: 16px 18px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  transition: all 0.25s ease;
  cursor: default;
}

.stat-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-blue {
  background: rgba(30, 58, 138, 0.08);
  color: #1e3a8a;
}

.icon-primary {
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
}

.icon-red {
  background: rgba(245, 63, 63, 0.08);
  color: #f53f3f;
}

.icon-green {
  background: rgba(16, 185, 129, 0.08);
  color: #10b981;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1.2;
  letter-spacing: -0.5px;
}

.stat-risk {
  color: #f53f3f;
}

.stat-label {
  font-size: 12px;
  color: #86909c;
  font-weight: 400;
}
</style>
