<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import { ElMessage } from 'element-plus'
import {
  DataAnalysis,
  Warning,
  Calendar,
  Timer,
  Download,
  Plus,
  TrendCharts,
  OfficeBuilding,
  Money,
  Document,
  ArrowRight,
  Refresh,
  Cpu,
} from '@element-plus/icons-vue'
import api from '@/api'
import { useModelStore, useUserStore } from '@/store'
import { formatDateTimeShort, formatDate } from '@/utils/format'
import SupplierProfileDrawer from '@/components/SupplierProfileDrawer.vue'

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------
interface InsightItem {
  type: 'danger' | 'info'
  tag: string
  content: string
  action_text: string
}

interface RadarData {
  indicators: { name: string; max: number }[]
  series: { value: number[]; name: string }[]
}

// ---------------------------------------------------------------------------
// Emits - 与父组件通信
// ---------------------------------------------------------------------------
const emit = defineEmits<{
  (e: 'new-task'): void
  (e: 'go-to-list', filter: 'all' | 'risk' | 'today'): void
  (e: 'generate-rectification', insight?: InsightItem): void
  (e: 'view-vendor-profile', vendorName?: string): void
}>()

// ---------------------------------------------------------------------------
// 当前模型信息 & 用户权限
// ---------------------------------------------------------------------------
const modelStore = useModelStore()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

// ---------------------------------------------------------------------------
// 数据卡片
// ---------------------------------------------------------------------------
const stats = ref({
  total: 0,
  risk: 0,
  today: 0,
  savedHours: 0,
})

const totalClauses = ref(12)

// ---------------------------------------------------------------------------
// 图表数据
// ---------------------------------------------------------------------------
const trendData = ref<{ dates: string[]; totals: number[]; risks: number[] }>({
  dates: [],
  totals: [],
  risks: [],
})

const pieData = ref<{ name: string; value: number }[]>([])
const radarData = ref<RadarData>({
  indicators: [
    { name: '财务', max: 100 },
    { name: '法务', max: 100 },
    { name: '交付', max: 100 },
    { name: '违约', max: 100 },
    { name: '信用', max: 100 },
  ],
  series: [{ value: [60, 60, 60, 60, 60], name: '平均得分' }],
})

// ---------------------------------------------------------------------------
// 智能洞察流数据
// ---------------------------------------------------------------------------
const insights = ref<InsightItem[]>([])
const insightsLoading = ref(false)
const lastAnalyzedAt = ref<string | null>(null)

// ---------------------------------------------------------------------------
// 异常记录
// ---------------------------------------------------------------------------
const recentAnomalies = ref<any[]>([])
const exportLoading = ref(false)

// ---------------------------------------------------------------------------
// 骨架屏加载状态
// ---------------------------------------------------------------------------
const radarLoading = ref(false)
const statsLoading = ref(false)

// ---------------------------------------------------------------------------
// ECharts 实例
// ---------------------------------------------------------------------------
const trendChartRef = ref<HTMLElement | null>(null)
const pieChartRef = ref<HTMLElement | null>(null)
const radarChartRef = ref<HTMLElement | null>(null)
const dashboardRef = ref<HTMLElement | null>(null)
const supplierDrawerRef = ref<InstanceType<typeof SupplierProfileDrawer> | null>(null)

let trendChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null
let radarChart: echarts.ECharts | null = null

// ---------------------------------------------------------------------------
// 报告生成时间
// ---------------------------------------------------------------------------
const reportTime = computed(() => formatDateTimeShort(new Date()))

// ---------------------------------------------------------------------------
// 渐变色配置
// ---------------------------------------------------------------------------
const getGradientColors = () => {
  return [
    new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#1890ff' },
      { offset: 1, color: '#36cfc9' },
    ]),
    new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#ff7d00' },
      { offset: 1, color: '#ffb500' },
    ]),
    new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#f53f3f' },
      { offset: 1, color: '#ff7875' },
    ]),
    new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#8543e0' },
      { offset: 1, color: '#b37feb' },
    ]),
    new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#2fc25b' },
      { offset: 1, color: '#6ee7b7' },
    ]),
  ]
}

// ---------------------------------------------------------------------------
// 初始化图表
// ---------------------------------------------------------------------------
const initCharts = () => {
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
    trendChart.setOption({
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e5e6eb',
        borderWidth: 1,
        textStyle: { color: '#1d2129' },
      },
      legend: {
        data: ['审查总数', '高风险数'],
        bottom: 0,
        textStyle: { color: '#4e5969' },
      },
      grid: {
        left: '2%',
        right: '2%',
        bottom: '10%',
        top: '12%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: trendData.value.dates,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#86909c', fontSize: 12 },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#86909c', fontSize: 12 },
        splitLine: { lineStyle: { color: '#f0f2f5', type: 'dashed' } },
      },
      series: [
        {
          name: '高风险数',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2, color: '#f53f3f' },
          itemStyle: { color: '#f53f3f', borderColor: '#fff', borderWidth: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(245, 63, 63, 0.12)' },
              { offset: 1, color: 'rgba(245, 63, 63, 0.02)' },
            ]),
          },
          data: trendData.value.risks,
        },
        {
          name: '审查总数',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2, color: '#1890ff' },
          itemStyle: { color: '#1890ff', borderColor: '#fff', borderWidth: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(24, 144, 255, 0.1)' },
              { offset: 1, color: 'rgba(24, 144, 255, 0.01)' },
            ]),
          },
          data: trendData.value.totals,
        },
      ],
    })
  }

  if (pieChartRef.value) {
    pieChart = echarts.init(pieChartRef.value)
    pieChart.setOption({
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e5e6eb',
        borderWidth: 1,
        textStyle: { color: '#1d2129' },
      },
      legend: {
        bottom: '5%',
        left: 'center',
        textStyle: { color: '#4e5969', fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 10,
      },
      color: getGradientColors(),
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: '46%',
          style: {
            text: String(totalClauses.value),
            fontSize: 28,
            fontWeight: 'bold',
            fill: '#1d2129',
            textAlign: 'center',
          },
        },
      ],
      series: [
        {
          name: '风险条款',
          type: 'pie',
          radius: ['45%', '65%'],
          center: ['50%', '48%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 8,
            borderColor: '#ffffff',
            borderWidth: 5,
          },
          label: { show: false, position: 'center' },
          emphasis: {
            label: { show: false },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.1)',
            },
          },
          labelLine: { show: false },
          data:
            pieData.value.length > 0
              ? pieData.value
              : [{ name: '暂无数据', value: 0 }],
        },
      ],
    })
  }

  // 初始化雷达图
  if (radarChartRef.value) {
    radarChart = echarts.init(radarChartRef.value)
    radarChart.setOption({
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e5e6eb',
        borderWidth: 1,
        textStyle: { color: '#1d2129' },
      },
      radar: {
        indicator: radarData.value.indicators,
        center: ['50%', '55%'],
        radius: '72%',
        axisName: {
          color: '#86909c',
          fontSize: 12,
        },
        splitArea: {
          areaStyle: {
            color: ['rgba(247, 248, 250, 0.5)', 'rgba(247, 248, 250, 0.3)'],
          },
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(134, 144, 156, 0.2)',
          },
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(134, 144, 156, 0.15)',
          },
        },
      },
      series: [
        {
          name: '风险维度评分',
          type: 'radar',
          data: [
            {
              value: radarData.value.series[0]?.value || [60, 60, 60, 60, 60],
              name: '近20份合同平均',
              symbol: 'circle',
              symbolSize: 8,
              lineStyle: {
                width: 2,
                color: '#1890ff',
              },
              itemStyle: {
                color: '#1890ff',
                borderColor: '#fff',
                borderWidth: 2,
              },
              areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: 'rgba(24, 144, 255, 0.4)' },
                  { offset: 1, color: 'rgba(24, 144, 255, 0.1)' },
                ]),
              },
              label: {
                show: true,
                fontSize: 11,
                fontWeight: 400,
                color: '#1d2129',
              },
            },
          ],
        },
      ],
    })
  }
}

// ---------------------------------------------------------------------------
// 加载 Dashboard 数据
// ---------------------------------------------------------------------------
const loadDashboardData = async () => {
  statsLoading.value = true
  try {
    const recordsParams: any = { page: 1, page_size: 5, risk_level: 'high' }
    if (isAdmin.value) {
      recordsParams.scope = 'all'
    }
    const [statsRes, trendRes, pieRes, recordsRes] = await Promise.all([
      api.get('/api/v1/stats'),
      api.get('/api/v1/chart/trend'),
      api.get('/api/v1/chart/clause-distribution'),
      api.get('/api/v1/records', { params: recordsParams }),
    ])

    const s = statsRes.data.data
    stats.value = {
      total: s.total_reviews,
      risk: Math.round(s.total_reviews * s.high_risk_ratio),
      today: s.today_new,
      savedHours: Math.round((s.total_reviews * 15) / 60),
    }

    trendData.value = trendRes.data.data
    pieData.value = pieRes.data.data

    totalClauses.value = pieData.value.reduce((sum, item) => sum + item.value, 0) || 12

    recentAnomalies.value = recordsRes.data.data.list || []
  } catch (_err) {
    ElMessage.error('Dashboard 数据加载失败，请检查后端服务')
  } finally {
    statsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 加载雷达图数据
// ---------------------------------------------------------------------------
const loadRadarData = async () => {
  radarLoading.value = true
  try {
    const res = await api.get('/api/v1/dashboard/stats')
    if (res.data.data?.radar) {
      radarData.value = res.data.data.radar
      // 更新雷达图
      if (radarChart) {
        radarChart.setOption({
          radar: {
            indicator: radarData.value.indicators,
          },
          series: [
            {
              data: [
                {
                  value: radarData.value.series[0]?.value || [60, 60, 60, 60, 60],
                  name: '近20份合同平均',
                  symbol: 'circle',
                  symbolSize: 8,
                  label: {
                    show: true,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#1d2129',
                  },
                },
              ],
            },
          ],
        })
      }
    }
  } catch (_err) {
    // 静默失败，使用默认值
  } finally {
    radarLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 获取最新洞察（从数据库读取）
// ---------------------------------------------------------------------------
const getLatestInsights = async () => {
  try {
    const res = await api.get('/api/v1/dashboard/insights/latest')
    if (res.data.code === 200) {
      const data = res.data.data
      insights.value = data.insights || []
      lastAnalyzedAt.value = data.generated_at || null
    }
  } catch (_err) {
    // 静默失败，使用空数组
    insights.value = []
    lastAnalyzedAt.value = null
  }
}

// ---------------------------------------------------------------------------
// 刷新洞察（调用 LLM 重新生成）
// ---------------------------------------------------------------------------
const refreshInsights = async () => {
  insightsLoading.value = true
  try {
    const res = await api.post('/api/v1/dashboard/insights/refresh')
    if (res.data.code === 200) {
      const data = res.data.data
      insights.value = data.insights || []
      lastAnalyzedAt.value = data.generated_at || null
      ElMessage.success('✨ AI 深度分析已完成')
    }
  } catch (_err) {
    ElMessage.error('洞察刷新失败，请稍后重试')
  } finally {
    insightsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// 处理刷新按钮点击
// ---------------------------------------------------------------------------
const handleRefresh = () => {
  refreshInsights()
}

const handleDirectProfile = () => {
  import('element-plus').then(({ ElMessageBox }) => {
    ElMessageBox.prompt('请输入供应商名称查询画像', '供应商画像档案', {
      confirmButtonText: '查询',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '供应商名称不能为空',
    })
      .then(({ value }) => {
        if (supplierDrawerRef.value) {
          supplierDrawerRef.value.open(value.trim())
        }
      })
      .catch(() => {})
  })
}

// ---------------------------------------------------------------------------
// 处理洞察卡片操作
// ---------------------------------------------------------------------------
const handleInsightAction = (insight: InsightItem) => {
  if (insight.tag.includes('付款') || insight.tag.includes('财务')) {
    emit('generate-rectification', insight)
  } else if (insight.tag.includes('供应商')) {
    // 从内容中提取供应商名称并打开画像抽屉
    const vendorMatch = insight.content.match(/([^，。]+?公司|[^，。]+?科技|[^，。]+?集团)/)
    const vendorName = vendorMatch ? vendorMatch[0] : undefined
    console.log('[Dashboard] 提取供应商名称:', vendorName, 'ref存在:', !!supplierDrawerRef.value)
    if (vendorName && supplierDrawerRef.value) {
      supplierDrawerRef.value.open(vendorName)
    } else if (!vendorName) {
      ElMessage.warning('无法从洞察内容中自动识别供应商名称，请手动输入')
      // 降级：弹出输入框让用户手动输入
      import('element-plus').then(({ ElMessageBox }) => {
        ElMessageBox.prompt('请输入供应商名称', '查看供应商画像', {
          confirmButtonText: '查询',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '供应商名称不能为空',
        })
          .then(({ value }) => {
            if (supplierDrawerRef.value) {
              supplierDrawerRef.value.open(value.trim())
            }
          })
          .catch(() => {})
      })
    } else if (!supplierDrawerRef.value) {
      ElMessage.error('抽屉组件未挂载，请刷新页面后重试')
    }
  } else {
    emit('go-to-list', 'risk')
  }
}

// ---------------------------------------------------------------------------
// 获取洞察图标
// ---------------------------------------------------------------------------
const getInsightIcon = (tag: string) => {
  if (tag.includes('付款') || tag.includes('财务')) return Money
  if (tag.includes('供应商')) return OfficeBuilding
  if (tag.includes('违约') || tag.includes('法务')) return Document
  return TrendCharts
}

// ---------------------------------------------------------------------------
// 获取洞察按钮文案
// ---------------------------------------------------------------------------
const getInsightButtonText = (tag: string) => {
  if (tag.includes('付款') || tag.includes('财务')) return '生成整改函'
  if (tag.includes('供应商')) return '查看供应商画像'
  return '查看详情'
}

// ---------------------------------------------------------------------------
// PDF 导出
// ---------------------------------------------------------------------------
const exportPdf = async () => {
  if (!dashboardRef.value) {
    ElMessage.error('导出失败：找不到报告内容')
    return
  }

  ElMessage.info('正在生成 PDF，请稍候...')
  exportLoading.value = true

  try {
    await nextTick()
    trendChart?.resize()
    pieChart?.resize()
    radarChart?.resize()
    await new Promise((resolve) => setTimeout(resolve, 800))

    const A4_WIDTH = 210
    const A4_HEIGHT = 297
    const MARGIN = 15
    const CONTENT_WIDTH = A4_WIDTH - MARGIN * 2
    const CONTENT_HEIGHT = A4_HEIGHT - MARGIN * 2

    const element = dashboardRef.value
    const rect = element.getBoundingClientRect()

    console.log('Export PDF - Element size:', rect.width, 'x', rect.height)

    if (rect.width === 0 || rect.height === 0) {
      throw new Error('报告内容尺寸为 0，无法导出')
    }

    const canvas = await html2canvas(element, {
      scale: 2,
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#ffffff',
      logging: false,
    })

    console.log('Export PDF - Canvas size:', canvas.width, 'x', canvas.height)

    if (canvas.width === 0 || canvas.height === 0) {
      throw new Error('截图失败，画布尺寸为 0')
    }

    const imgData = canvas.toDataURL('image/png')
    const imgWidth = canvas.width
    const imgHeight = canvas.height
    const imgWidthMm = imgWidth / 5.67
    const imgHeightMm = imgHeight / 5.67

    const pdf = new jsPDF('p', 'mm', 'a4')
    const scaleRatio = CONTENT_WIDTH / imgWidthMm
    const scaledHeight = imgHeightMm * scaleRatio

    addPageHeader(pdf, 0)

    if (scaledHeight <= CONTENT_HEIGHT - 20) {
      pdf.addImage(imgData, 'PNG', MARGIN, 45, CONTENT_WIDTH, scaledHeight)
      addPageFooter(pdf, 1)
    } else {
      const pageContentHeightMm = CONTENT_HEIGHT - 45
      const totalPages = Math.ceil(scaledHeight / pageContentHeightMm)

      for (let i = 0; i < totalPages; i++) {
        if (i > 0) {
          pdf.addPage()
          addPageHeader(pdf, i)
        }

        const remainingHeight = scaledHeight - (i * pageContentHeightMm)
        const destHeight = Math.min(remainingHeight, pageContentHeightMm)

        pdf.addImage(imgData, 'PNG', MARGIN, 45, CONTENT_WIDTH, destHeight)
        addPageFooter(pdf, i + 1)
      }
    }

    const filename = `智契数据驾驶舱报告_${formatDate(new Date())}.pdf`
    pdf.save(filename)
    ElMessage.success('PDF 导出成功')
  } catch (error: any) {
    console.error('PDF 导出失败:', error)
    ElMessage.error(`PDF 导出失败: ${error.message || '未知错误'}`)
  } finally {
    exportLoading.value = false
  }
}

const addPageHeader = (pdf: jsPDF, pageIndex: number) => {
  pdf.setDrawColor(200, 200, 200)
  pdf.setLineWidth(0.5)
  pdf.line(15, 8, 195, 8)

  if (pageIndex === 0) {
    pdf.setFillColor(30, 58, 138)
    pdf.rect(15, 12, 4, 10, 'F')

    pdf.setFontSize(18)
    pdf.setTextColor(30, 58, 138)
    pdf.text('智契 SMARTPACT', 22, 20)

    pdf.setFontSize(10)
    pdf.setTextColor(120, 120, 120)
    pdf.text(`报告生成时间：${reportTime.value}`, 15, 32)

    pdf.setDrawColor(220, 53, 69)
    pdf.setLineWidth(0.5)
    pdf.rect(140, 27, 55, 8)
    pdf.setTextColor(220, 53, 69)
    pdf.setFontSize(9)
    pdf.text('内部审计机密文件', 142, 32.5)
  } else {
    pdf.setFontSize(12)
    pdf.setTextColor(30, 58, 138)
    pdf.text('智契 SMARTPACT', 15, 18)

    pdf.setFontSize(9)
    pdf.setTextColor(120, 120, 120)
    pdf.text('内部审计机密文件', 160, 18)
  }

  pdf.setDrawColor(200, 200, 200)
  pdf.setLineWidth(0.5)
  pdf.line(15, pageIndex === 0 ? 40 : 22, 195, pageIndex === 0 ? 40 : 22)
}

const addPageFooter = (pdf: jsPDF, pageNum: number) => {
  pdf.setDrawColor(200, 200, 200)
  pdf.setLineWidth(0.3)
  pdf.line(15, 282, 195, 282)

  pdf.setFontSize(8)
  pdf.setTextColor(134, 144, 156)
  pdf.text('智契 SMARTPACT · 智能合规审查系统 · 本文件由系统自动生成', 15, 287)
  pdf.text(`第 ${pageNum} 页`, 180, 287)
}

const handleBeforePrint = () => {
  setTimeout(() => {
    trendChart?.resize()
    pieChart?.resize()
    radarChart?.resize()
  }, 100)
}

const handleAfterPrint = () => {
  trendChart?.resize()
  pieChart?.resize()
  radarChart?.resize()
}

const handleCardClick = (type: 'all' | 'risk' | 'today') => {
  emit('go-to-list', type)
}

const handleNewTask = () => {
  emit('new-task')
}

const handleResize = () => {
  trendChart?.resize()
  pieChart?.resize()
  radarChart?.resize()
}

onMounted(async () => {
  if (modelStore.models.length === 0) {
    await modelStore.fetchModels()
  }
  await loadDashboardData()
  await loadRadarData()
  await getLatestInsights()
  nextTick(() => initCharts())
  window.addEventListener('resize', handleResize)
  if (window.matchMedia) {
    const mediaQueryList = window.matchMedia('print')
    mediaQueryList.addEventListener('change', (mql) => {
      if (mql.matches) {
        handleBeforePrint()
      } else {
        handleAfterPrint()
      }
    })
  }
  window.addEventListener('beforeprint', handleBeforePrint)
  window.addEventListener('afterprint', handleAfterPrint)
})

onUnmounted(() => {
  trendChart?.dispose()
  pieChart?.dispose()
  radarChart?.dispose()
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('beforeprint', handleBeforePrint)
  window.removeEventListener('afterprint', handleAfterPrint)
})
</script>

<template>
  <div ref="dashboardRef" class="dashboard-container">
    <!-- 打印专用页眉 -->
    <div class="print-header">
      <div class="print-logo">
        <span class="print-logo-icon">智</span>
        <span class="print-logo-text">智契 SMARTPACT</span>
      </div>
      <div class="print-meta">
        <div class="print-time">报告生成时间：{{ reportTime }}</div>
        <div class="print-watermark">内部审计机密文件 · 严禁外传</div>
      </div>
    </div>

    <!-- 顶部标题 + 操作按钮 -->
    <header class="dashboard-header no-print">
      <div class="header-title">
        <h2 class="dashboard-title">数据驾驶舱</h2>
        <p class="dashboard-subtitle">实时风控数据监控与趋势分析</p>
      </div>
      <div class="header-actions">
        <div v-if="modelStore.currentModel" class="current-model-tag">
          <el-tag type="primary" effect="light" size="small">
            <el-icon><Cpu /></el-icon>
            <span class="model-name">{{ modelStore.currentModel.name }}</span>
          </el-tag>
        </div>
        <el-button type="primary" class="new-task-btn" @click="handleNewTask">
          <el-icon><Plus /></el-icon>
          新建比对任务
        </el-button>
        <el-button
          class="export-btn"
          :loading="exportLoading"
          @click="exportPdf"
        >
          <el-icon><Download /></el-icon>
          导出报告
        </el-button>
      </div>
    </header>

    <!-- 顶部数据卡片 -->
    <section class="stats-section report-section">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="6">
          <el-skeleton :rows="2" animated v-if="statsLoading">
            <template #template>
              <div class="stat-card skeleton-card">
                <el-skeleton-item variant="circle" class="skeleton-icon" />
                <div class="skeleton-text">
                  <el-skeleton-item variant="h3" style="width: 60px" />
                  <el-skeleton-item variant="text" style="width: 100px; margin-top: 8px" />
                </div>
              </div>
            </template>
          </el-skeleton>
          <div v-else class="stat-card" @click="handleCardClick('all')">
            <div class="stat-icon icon-blue">
              <el-icon :size="22"><DataAnalysis /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.total }}</div>
              <div class="stat-label">累计审查总数</div>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-skeleton :rows="2" animated v-if="statsLoading">
            <template #template>
              <div class="stat-card skeleton-card">
                <el-skeleton-item variant="circle" class="skeleton-icon" />
                <div class="skeleton-text">
                  <el-skeleton-item variant="h3" style="width: 60px" />
                  <el-skeleton-item variant="text" style="width: 100px; margin-top: 8px" />
                </div>
              </div>
            </template>
          </el-skeleton>
          <div v-else class="stat-card" @click="handleCardClick('risk')">
            <div class="stat-icon icon-red">
              <el-icon :size="22"><Warning /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value stat-risk">{{ stats.risk }}</div>
              <div class="stat-label">高风险合同数</div>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-skeleton :rows="2" animated v-if="statsLoading">
            <template #template>
              <div class="stat-card skeleton-card">
                <el-skeleton-item variant="circle" class="skeleton-icon" />
                <div class="skeleton-text">
                  <el-skeleton-item variant="h3" style="width: 60px" />
                  <el-skeleton-item variant="text" style="width: 100px; margin-top: 8px" />
                </div>
              </div>
            </template>
          </el-skeleton>
          <div v-else class="stat-card" @click="handleCardClick('today')">
            <div class="stat-icon icon-green">
              <el-icon :size="22"><Calendar /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.today }}</div>
              <div class="stat-label">今日新增审查</div>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-skeleton :rows="2" animated v-if="statsLoading">
            <template #template>
              <div class="stat-card skeleton-card">
                <el-skeleton-item variant="circle" class="skeleton-icon" />
                <div class="skeleton-text">
                  <el-skeleton-item variant="h3" style="width: 60px" />
                  <el-skeleton-item variant="text" style="width: 100px; margin-top: 8px" />
                </div>
              </div>
            </template>
          </el-skeleton>
          <div v-else class="stat-card stat-card--static">
            <div class="stat-icon icon-purple">
              <el-icon :size="22"><Timer /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.savedHours }}h</div>
              <div class="stat-label">累计节省工时</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </section>

    <!-- 中间图表区 -->
    <section class="charts-section report-section">
      <el-row :gutter="16">
        <el-col :xs="24" :lg="12">
          <div class="chart-card">
            <div class="chart-header">
              <div class="chart-title-wrap">
                <span class="chart-title">近7天风险趋势</span>
                <span class="chart-subtitle">Trend of the last 7 days</span>
              </div>
            </div>
            <div ref="trendChartRef" class="chart-box"></div>
          </div>
        </el-col>
        <el-col :xs="24" :lg="6">
          <div class="chart-card">
            <div class="chart-header">
              <div class="chart-title-wrap">
                <span class="chart-title" title="风险条款分布">风险条款分布</span>
                <span class="chart-subtitle">Clause distribution</span>
              </div>
            </div>
            <div ref="pieChartRef" class="chart-box"></div>
          </div>
        </el-col>
        <el-col :xs="24" :lg="6">
          <div class="chart-card radar-card">
            <div class="chart-header">
              <div class="chart-title-wrap">
                <span class="chart-title" title="多维风险雷达(20份合同平均)">多维风险雷达</span>
                <span class="chart-subtitle">Risk Radar</span>
              </div>
            </div>
            <!-- 雷达图骨架屏 -->
            <div v-if="radarLoading" class="radar-skeleton">
              <el-skeleton :rows="5" animated>
                <template #template>
                  <div class="radar-skeleton-content">
                    <div class="radar-skeleton-center">
                      <el-skeleton-item variant="circle" style="width: 60px; height: 60px" />
                    </div>
                    <div class="radar-skeleton-axes">
                      <el-skeleton-item variant="text" style="width: 40px" />
                      <el-skeleton-item variant="text" style="width: 40px" />
                      <el-skeleton-item variant="text" style="width: 40px" />
                      <el-skeleton-item variant="text" style="width: 40px" />
                      <el-skeleton-item variant="text" style="width: 40px" />
                    </div>
                  </div>
                </template>
              </el-skeleton>
              <div class="radar-skeleton-text">AI 正在计算风险维度...</div>
            </div>
            <div v-else ref="radarChartRef" class="chart-box radar-box"></div>
          </div>
        </el-col>
      </el-row>
    </section>

    <!-- 底部异常记录 -->
    <section class="anomaly-section report-section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title-wrap">
            <el-icon :size="16" color="#f53f3f"><Warning /></el-icon>
            <span class="table-title">最近 5 条异常比对记录</span>
          </div>
        </div>
        <el-table
          :data="recentAnomalies"
          style="width: 100%"
          empty-text="暂无异常记录"
          :header-cell-style="{
            background: '#f7f8fa',
            color: '#4e5969',
            fontWeight: 600,
            fontSize: '13px',
          }"
        >
          <el-table-column
            prop="project_name"
            label="项目名称"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column prop="created_at" label="创建时间" width="170" />
          <el-table-column prop="risk_level" label="风险等级" width="100">
            <template #default>
              <el-tag type="danger" size="small" effect="light">高风险</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="conclusion"
            label="异常摘要"
            min-width="280"
            show-overflow-tooltip
          />
        </el-table>
      </div>
    </section>

    <!-- 智契 Smart Feed - AI 智能洞察流 -->
    <section class="insights-section report-section no-print">
      <div class="insights-card">
        <div class="insights-header">
          <div class="insights-title-wrap">
            <div class="insights-icon">
              <el-icon :size="20"><TrendCharts /></el-icon>
            </div>
            <div class="insights-title-group">
              <span class="insights-title">智契 Smart Feed</span>
              <span class="insights-subtitle">AI 智能洞察流</span>
            </div>
          </div>
          <div class="insights-header-actions">
            <el-tag type="info" size="small" effect="plain" v-if="!insightsLoading">
              基于最近20份合同
            </el-tag>
            <el-button
              type="warning"
              link
              size="small"
              @click="handleDirectProfile"
            >
              <el-icon><OfficeBuilding /></el-icon>
              <span class="refresh-text">供应商画像</span>
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              :loading="insightsLoading"
              :disabled="insightsLoading"
              @click="handleRefresh"
            >
              <el-icon><Refresh /></el-icon>
              <span class="refresh-text">重新进行深度分析</span>
            </el-button>
          </div>
        </div>

        <!-- 洞察流骨架屏 -->
        <div v-if="insightsLoading" class="insights-skeleton">
          <div v-for="i in 2" :key="i" class="insight-skeleton-item">
            <el-skeleton animated>
              <template #template>
                <div class="skeleton-insight-card">
                  <div class="skeleton-insight-header">
                    <el-skeleton-item variant="circle" style="width: 32px; height: 32px" />
                    <el-skeleton-item variant="text" style="width: 120px; margin-left: 12px" />
                  </div>
                  <el-skeleton-item variant="p" style="width: 100%; margin-top: 12px" />
                  <el-skeleton-item variant="p" style="width: 80%; margin-top: 8px" />
                  <el-skeleton-item variant="button" style="width: 100px; margin-top: 12px" />
                </div>
              </template>
            </el-skeleton>
          </div>
          <div class="insights-skeleton-text">AI 正在分析宏观风险规律...</div>
        </div>

        <!-- 洞察流内容 -->
        <div v-else class="insights-timeline">
          <div
            v-for="(insight, index) in insights"
            :key="index"
            class="insight-item"
            :class="{ 'insight-danger': insight.type === 'danger' }"
          >
            <div class="insight-timeline-line" v-if="index < insights.length - 1"></div>
            <div class="insight-timeline-dot" :class="`dot-${insight.type}`">
              <el-icon :size="14">
                <component :is="getInsightIcon(insight.tag)" />
              </el-icon>
            </div>
            <div class="insight-content">
              <div class="insight-header">
                <el-tag
                  :type="insight.type === 'danger' ? 'danger' : 'info'"
                  size="small"
                  effect="light"
                >
                  {{ insight.tag }}
                </el-tag>
              </div>
              <p class="insight-text">{{ insight.content }}</p>
              <div class="insight-action">
                <el-button
                  :type="insight.type === 'danger' ? 'danger' : 'primary'"
                  size="small"
                  text
                  @click="handleInsightAction(insight)"
                >
                  {{ getInsightButtonText(insight.tag) }}
                  <el-icon class="el-icon--right"><ArrowRight /></el-icon>
                </el-button>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <el-empty
            v-if="insights.length === 0"
            description="暂无洞察数据"
            :image-size="80"
          />
        </div>

        <!-- 上次分析时间 -->
        <div v-if="lastAnalyzedAt" class="insights-footer">
          <span class="last-analyzed-time">
            上次分析时间：{{ formatDateTimeShort(lastAnalyzedAt) }}
          </span>
        </div>
      </div>
    </section>

    <!-- 打印专用页脚 -->
    <div class="print-footer">
      <div class="print-footer-line"></div>
      <div class="print-footer-text">
        智契 SMARTPACT · 智能合规审查系统 · 本文件由系统自动生成
      </div>
    </div>

    <!-- 供应商画像抽屉 -->
    <SupplierProfileDrawer ref="supplierDrawerRef" />
  </div>
</template>

<style scoped>
.dashboard-container {
  min-height: calc(100vh - 64px);
  background: #f7f8fa;
  padding: 24px;
  box-sizing: border-box;
}

.report-section {
  background: #ffffff;
  margin-bottom: 16px;
}

.print-header,
.print-footer {
  display: none;
}

@media print {
  @page {
    size: A4 portrait;
    margin: 15mm 12mm;
  }

  .dashboard-container {
    background: #ffffff !important;
    padding: 0 !important;
  }

  .print-header {
    display: flex !important;
    justify-content: space-between;
    align-items: flex-start;
    padding-bottom: 20px;
    border-bottom: 2px solid #1e3a8a;
    margin-bottom: 24px;
  }

  .print-logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .print-logo-icon {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    color: white;
    font-size: 20px;
    font-weight: bold;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
  }

  .print-logo-text {
    font-size: 22px;
    font-weight: 700;
    color: #1e3a8a;
    letter-spacing: 0.5px;
  }

  .print-meta {
    text-align: right;
  }

  .print-time {
    font-size: 12px;
    color: #4e5969;
    margin-bottom: 4px;
  }

  .print-watermark {
    font-size: 11px;
    color: #dc2626;
    font-weight: 600;
    padding: 4px 12px;
    border: 1px solid #dc2626;
    border-radius: 4px;
    display: inline-block;
  }

  .print-footer {
    display: block !important;
    margin-top: 30px;
    padding-top: 16px;
    border-top: 1px solid #e5e6eb;
  }

  .print-footer-text {
    font-size: 10px;
    color: #86909c;
    text-align: center;
  }

  .no-print {
    display: none !important;
  }

  .stat-card,
  .chart-card,
  .table-card,
  .insights-card {
    break-inside: avoid;
    page-break-inside: avoid;
    box-shadow: none !important;
    border: 1px solid #e5e6eb !important;
  }
}

/* ============================================================================
   顶部标题栏
   ============================================================================ */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dashboard-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #1d2129;
  letter-spacing: 0.5px;
}

.dashboard-subtitle {
  margin: 0;
  font-size: 13px;
  color: #86909c;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.current-model-tag :deep(.el-tag) {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  padding: 0 10px;
  height: 32px;
  border-radius: 6px;
}

.model-name {
  margin-left: 2px;
}

.new-task-btn {
  background: #1e3a8a;
  border: none;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  padding: 10px 18px;
  box-shadow: 0 2px 8px rgba(30, 58, 138, 0.2);
  transition: all 0.25s ease;
}

.new-task-btn:hover {
  background: #2563eb;
  box-shadow: 0 4px 12px rgba(30, 58, 138, 0.3);
  transform: translateY(-1px);
}

.export-btn {
  background: #ffffff;
  border: 1px solid #1e3a8a;
  color: #1e3a8a;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  padding: 10px 18px;
  transition: all 0.25s ease;
}

.export-btn:hover {
  background: rgba(30, 58, 138, 0.04);
  border-color: #2563eb;
  color: #2563eb;
}

/* ============================================================================
   数据卡片
   ============================================================================ */
.stats-section {
  margin-bottom: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 20px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  transition: all 0.25s ease;
  cursor: pointer;
  margin-bottom: 16px;
}

.stat-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.stat-card--static {
  cursor: default;
}

.stat-card--static:hover {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  transform: none;
}

/* 骨架屏样式 */
.skeleton-card {
  cursor: default;
}

.skeleton-card:hover {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  transform: none;
}

.skeleton-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  flex-shrink: 0;
}

.skeleton-text {
  display: flex;
  flex-direction: column;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-blue {
  background: rgba(24, 144, 255, 0.08);
  color: #1890ff;
}

.icon-red {
  background: rgba(240, 72, 100, 0.08);
  color: #f04864;
}

.icon-green {
  background: rgba(47, 194, 91, 0.08);
  color: #2fc25b;
}

.icon-purple {
  background: rgba(133, 67, 224, 0.08);
  color: #8543e0;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1.2;
  letter-spacing: -0.5px;
}

.stat-risk {
  color: #f04864;
}

.stat-label {
  font-size: 13px;
  color: #86909c;
  font-weight: 400;
}

/* ============================================================================
   图表区
   ============================================================================ */
.charts-section {
  margin-bottom: 16px;
}

.chart-card {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  padding: 20px;
  margin-bottom: 16px;
  transition: box-shadow 0.25s ease;
  height: 380px;
  display: flex;
  flex-direction: column;
}

.chart-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.radar-card {
  position: relative;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.chart-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.chart-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  white-space: nowrap;
}

.chart-subtitle {
  font-size: 12px;
  color: #c9cdd4;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.chart-subtitle {
  font-size: 12px;
  color: #c9cdd4;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.chart-box {
  width: 100%;
  flex: 1;
  min-height: 280px;
}

.radar-box {
  flex: 1;
  min-height: 260px;
}

/* 雷达图骨架屏 */
.radar-skeleton {
  height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.radar-skeleton-content {
  position: relative;
  width: 200px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.radar-skeleton-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.radar-skeleton-axes {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 10px;
}

.radar-skeleton-text {
  margin-top: 16px;
  font-size: 13px;
  color: #86909c;
  text-align: center;
}

/* ============================================================================
   异常记录
   ============================================================================ */
.anomaly-section {
  margin-bottom: 16px;
}

.table-card {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  padding: 20px;
  transition: box-shadow 0.25s ease;
}

.table-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.table-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

:deep(.el-table) {
  border-radius: 6px;
  overflow: hidden;
}

:deep(.el-table__row) {
  transition: background 0.2s ease;
}

:deep(.el-table__row:hover > td) {
  background: #f7f8fa !important;
}

:deep(.el-tag--danger) {
  background: rgba(240, 72, 100, 0.08);
  border-color: rgba(240, 72, 100, 0.2);
  color: #f04864;
}

/* ============================================================================
   智契 Smart Feed - AI 智能洞察流
   ============================================================================ */
.insights-section {
  margin-bottom: 12px;
}

.insights-card {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.03);
  padding: 20px;
  transition: box-shadow 0.25s ease;
}

.insights-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.insights-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f2f5;
}

.insights-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.refresh-text {
  margin-left: 4px;
  font-size: 13px;
}

/* 洞察流底部 */
.insights-footer {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
  text-align: right;
}

.last-analyzed-time {
  font-size: 12px;
  color: #86909c;
}

.insights-title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.insights-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.insights-title-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.insights-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2129;
}

.insights-subtitle {
  font-size: 12px;
  color: #86909c;
}

/* 洞察骨架屏 */
.insights-skeleton {
  padding: 20px 0;
}

.insight-skeleton-item {
  margin-bottom: 20px;
}

.skeleton-insight-card {
  padding: 16px;
  background: #f7f8fa;
  border-radius: 8px;
  border: 1px solid #e5e6eb;
}

.skeleton-insight-header {
  display: flex;
  align-items: center;
}

.insights-skeleton-text {
  text-align: center;
  font-size: 13px;
  color: #86909c;
  margin-top: 16px;
}

/* 洞察时间线 */
.insights-timeline {
  position: relative;
  padding: 8px 0;
}

.insight-item {
  position: relative;
  display: flex;
  gap: 16px;
  padding: 16px 0;
}

.insight-timeline-line {
  position: absolute;
  left: 15px;
  top: 48px;
  bottom: -8px;
  width: 2px;
  background: #e5e6eb;
}

.insight-timeline-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  z-index: 1;
}

.dot-danger {
  background: rgba(245, 63, 63, 0.1);
  color: #f53f3f;
  border: 2px solid rgba(245, 63, 63, 0.2);
}

.dot-info {
  background: rgba(24, 144, 255, 0.1);
  color: #1890ff;
  border: 2px solid rgba(24, 144, 255, 0.2);
}

.insight-content {
  flex: 1;
  padding: 16px 20px;
  background: #f7f8fa;
  border-radius: 8px;
  border: 1px solid #f0f2f5;
  transition: all 0.25s ease;
}

.insight-content:hover {
  background: #ffffff;
  border-color: #e5e6eb;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.insight-danger .insight-content {
  background: rgba(245, 63, 63, 0.02);
  border-color: rgba(245, 63, 63, 0.1);
}

.insight-danger .insight-content:hover {
  background: rgba(245, 63, 63, 0.04);
  border-color: rgba(245, 63, 63, 0.2);
}

.insight-header {
  margin-bottom: 10px;
}

.insight-text {
  font-size: 14px;
  color: #4e5969;
  line-height: 1.7;
  margin: 0;
}

.insight-action {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
    padding: 12px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 8px;
  }

  .stats-section {
    padding: 8px 12px;
    margin-bottom: 8px;
  }

  .stat-card {
    margin-bottom: 0;
    padding: 12px 8px;
    gap: 6px;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .stat-icon {
    width: 32px;
    height: 32px;
  }

  .stat-icon .el-icon {
    font-size: 16px;
  }

  .stat-info {
    align-items: center;
    gap: 2px;
  }

  .stat-value {
    font-size: 18px;
  }

  .stat-label {
    font-size: 11px;
  }

  .dashboard-title {
    font-size: 18px;
  }

  .dashboard-subtitle {
    font-size: 12px;
  }

  .risk-pie-col,
  .risk-trend-col,
  .risk-insight-col {
    margin-bottom: 12px;
  }

  .insight-item {
    flex-direction: column;
    gap: 8px;
  }

  .insight-icon {
    align-self: flex-start;
  }

  .recent-section {
    padding: 12px;
  }

  .recent-table :deep(.el-table__header-wrapper th) {
    padding: 8px 4px;
    font-size: 12px;
  }

  .recent-table :deep(.el-table__body-wrapper td) {
    padding: 8px 4px;
    font-size: 12px;
  }

  .contract-name-text {
    max-width: 80px;
  }

  .current-model-tag {
    display: none;
  }

  /* 表格横向滚动 */
  .recent-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
  }

  /* 洞察流头部换行 */
  .insights-header {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }

  .insights-header-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }

  .insights-header-actions .refresh-text {
    display: none;
  }

  /* 顶部统计卡片改为 2x2 网格 */
  .stats-section :deep(.el-row) {
    flex-wrap: wrap;
    margin-left: -6px !important;
    margin-right: -6px !important;
  }

  .stats-section :deep(.el-col) {
    width: 50% !important;
    max-width: 50% !important;
    flex: 0 0 50% !important;
    padding-left: 6px !important;
    padding-right: 6px !important;
    margin-bottom: 8px;
    min-width: auto;
  }

  /* 缩小 empty 区域 */
  :deep(.el-empty) {
    padding: 20px 0;
  }

  :deep(.el-empty__image) {
    width: 80px;
  }

  :deep(.el-empty__description) {
    font-size: 13px;
  }

  /* 缩小图表卡片 */
  .chart-card {
    height: 280px;
    padding: 12px;
    margin-bottom: 8px;
  }

  .charts-section {
    margin-bottom: 8px;
  }

  .report-section {
    margin-bottom: 8px;
  }

  .recent-section {
    padding: 8px 12px;
  }
}
</style>