<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { useAuthStore } from '../stores/auth'
import { getUsers, type UserItem } from '../api/users'
import {
  getMetricsAgents,
  getMetricsSkills,
  getMetricsOverview,
  getMetricsTrends,
  type MetricsAgents,
  type MetricsErrorItem,
  type MetricsRangeParams,
  type MetricsSummary,
  type MetricsTokenItem,
} from '../api/metrics'

use([
  CanvasRenderer,
  LineChart,
  PieChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
])

const DASHBOARD_RANGE_KEY = 'admin_dashboard_range'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const loading = ref(false)
const range = ref<string[]>([])
const errorMessage = ref('')
const errorChartType = ref<'pie' | 'bar'>('pie')

const scopeMode = ref<'all' | 'user'>('all')
const selectedUserId = ref<string>('')
const users = ref<UserItem[]>([])

const quickRanges = [
  {
    label: '近 7 天',
    value: 7,
  },
  {
    label: '近 30 天',
    value: 30,
  },
]

const summary = ref<MetricsSummary>({
  p95_ms: 0,
  success_rate: 0,
  token_total: 0,
  agent_created: 0,
})
const previousSummary = ref<MetricsSummary | null>(null)
const tokenSeries = ref<MetricsTokenItem[]>([])
const topErrors = ref<MetricsErrorItem[]>([])
const agentStats = ref<MetricsAgents>({ created: 0, used: 0, retention_7d: 0 })

const formatDate = (d: Date): string => {
  const y = d.getFullYear()
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${y}-${m}-${day}`
}

const parseDate = (value: string): Date => {
  const [y, m, d] = value.split('-').map((part) => Number(part))
  return new Date(y, (m || 1) - 1, d || 1)
}

const saveRange = (value: string[]) => {
  localStorage.setItem(DASHBOARD_RANGE_KEY, JSON.stringify(value))
}

const loadSavedRange = (): string[] | null => {
  try {
    const raw = localStorage.getItem(DASHBOARD_RANGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.length === 2) {
      return [parsed[0], parsed[1]]
    }
    return null
  } catch {
    return null
  }
}

const getRangeParams = (): MetricsRangeParams => {
  if (!range.value || range.value.length !== 2) {
    const end = new Date()
    const start = new Date(end)
    start.setDate(start.getDate() - 6)
    return {
      start_date: formatDate(start),
      end_date: formatDate(end),
    }
  }
  return {
    start_date: range.value[0],
    end_date: range.value[1],
  }
}

const getScopeParams = (): Pick<MetricsRangeParams, 'scope' | 'user_id'> => {
  if (!isAdmin.value) {
    return { scope: 'self', user_id: authStore.user?.id }
  }
  if (scopeMode.value === 'user' && selectedUserId.value) {
    return { scope: 'self', user_id: selectedUserId.value }
  }
  return { scope: 'all' }
}

const getPreviousRangeParams = (params: MetricsRangeParams): MetricsRangeParams | null => {
  if (!params.start_date || !params.end_date) return null
  const start = parseDate(params.start_date)
  const end = parseDate(params.end_date)
  const days = Math.max(1, Math.floor((end.getTime() - start.getTime()) / 86400000) + 1)

  const previousEnd = new Date(start)
  previousEnd.setDate(previousEnd.getDate() - 1)
  const previousStart = new Date(previousEnd)
  previousStart.setDate(previousStart.getDate() - (days - 1))

  return {
    start_date: formatDate(previousStart),
    end_date: formatDate(previousEnd),
    ...getScopeParams(),
  }
}

const getDeltaText = (current: number, previous: number | null, suffix = '') => {
  if (previous === null || previous === undefined) return '暂无对比数据'
  const delta = current - previous
  if (Math.abs(delta) < 1e-6) return `环比持平 ${suffix}`.trim()
  const sign = delta > 0 ? '↑' : '↓'
  const abs = Math.abs(delta)
  return `${sign} ${abs.toFixed(2)}${suffix}`
}

const successRateDeltaText = computed(() => {
  if (!previousSummary.value) return '暂无对比数据'
  return getDeltaText(summary.value.success_rate * 100, previousSummary.value.success_rate * 100, '%')
})

const p95DeltaText = computed(() => {
  if (!previousSummary.value) return '暂无对比数据'
  return getDeltaText(summary.value.p95_ms, previousSummary.value.p95_ms, 'ms')
})

const successRateDeltaClass = computed(() => {
  if (!previousSummary.value) return 'delta-neutral'
  if (summary.value.success_rate > previousSummary.value.success_rate) return 'delta-up'
  if (summary.value.success_rate < previousSummary.value.success_rate) return 'delta-down'
  return 'delta-neutral'
})

const p95DeltaClass = computed(() => {
  if (!previousSummary.value) return 'delta-neutral'
  if (summary.value.p95_ms < previousSummary.value.p95_ms) return 'delta-up'
  if (summary.value.p95_ms > previousSummary.value.p95_ms) return 'delta-down'
  return 'delta-neutral'
})

const scopeLabel = computed(() => {
  if (!isAdmin.value) return '数据范围：当前账号'
  if (scopeMode.value === 'user' && selectedUserId.value) {
    const hit = users.value.find((u) => u.id === selectedUserId.value)
    return `数据范围：用户 ${hit?.username || selectedUserId.value}`
  }
  return '数据范围：全量（管理员）'
})

const loadUsers = async () => {
  if (!isAdmin.value) return
  try {
    const response = await getUsers({ page: 1, page_size: 200 })
    const data = (response as any)?.data ?? response
    const list = Array.isArray(data?.list) ? data.list : []
    users.value = list
  } catch {
    users.value = []
  }
}

const fetchAll = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const params = { ...getRangeParams(), ...getScopeParams() }
    const previousParams = getPreviousRangeParams(params)

    const [summaryData, errorsData, tokensData, agentsData, previousSummaryData] = await Promise.all([
      getMetricsOverview(params),
      getMetricsSkills(params),
      getMetricsTrends(params),
      getMetricsAgents(params),
      previousParams ? getMetricsOverview(previousParams) : Promise.resolve(null),
    ])

    summary.value = summaryData
    previousSummary.value = previousSummaryData
    topErrors.value = Array.isArray(errorsData?.top_errors) ? errorsData.top_errors : []
    tokenSeries.value = Array.isArray(tokensData) ? tokensData : []
    agentStats.value = agentsData

    if (range.value?.length === 2) {
      saveRange(range.value)
    }
  } catch {
    summary.value = { p95_ms: 0, success_rate: 0, token_total: 0, agent_created: 0 }
    previousSummary.value = null
    topErrors.value = []
    tokenSeries.value = []
    agentStats.value = { created: 0, used: 0, retention_7d: 0 }
    errorMessage.value = '看板数据加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

const tokenLineOption = computed(() => ({
  title: { text: '每日 Token 消耗趋势', textStyle: { color: '#E9EEFF' } },
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 55, bottom: 40 },
  xAxis: {
    type: 'category',
    axisLabel: { color: '#9BA8CF' },
    axisLine: { lineStyle: { color: '#30406A' } },
    data: tokenSeries.value.map((item) => item.date),
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#9BA8CF' },
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
  },
  series: [
    {
      type: 'line',
      smooth: true,
      itemStyle: { color: '#6D5EF8' },
      areaStyle: { color: 'rgba(109,94,248,0.28)' },
      data: tokenSeries.value.map((item) => item.tokens),
    },
  ],
}))

const errorOption = computed(() => {
  if (errorChartType.value === 'bar') {
    return {
      title: { text: '请求错误分布（柱状图）', textStyle: { color: '#E9EEFF' } },
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 55, bottom: 40 },
      xAxis: {
        type: 'category',
        axisLabel: { color: '#9BA8CF' },
        axisLine: { lineStyle: { color: '#30406A' } },
        data: topErrors.value.map((item) => `${item.code}`),
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#9BA8CF' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      },
      series: [
        {
          type: 'bar',
          itemStyle: { color: '#FF5D73' },
          data: topErrors.value.map((item) => item.count),
          barWidth: 24,
        },
      ],
    }
  }

  return {
    title: { text: '请求错误分布（饼图）', textStyle: { color: '#E9EEFF' } },
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: '#C9D3F2' } },
    series: [
      {
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['40%', '50%'],
        data: topErrors.value.map((item) => ({
          name: `${item.code}`,
          value: item.count,
        })),
      },
    ],
  }
})

const applyQuickRange = (days: number) => {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - (days - 1))
  range.value = [formatDate(start), formatDate(end)]
  fetchAll()
}

const onRangeChange = () => {
  fetchAll()
}

const onRetry = () => {
  fetchAll()
}

const onScopeChange = () => {
  if (scopeMode.value === 'all') {
    selectedUserId.value = ''
  }
  fetchAll()
}

const onTargetUserChange = () => {
  fetchAll()
}

const escapeCsvValue = (value: string | number) => {
  const text = String(value ?? '')
  if (text.includes(',') || text.includes('"') || text.includes('\n')) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const exportCsv = () => {
  const params = getRangeParams()
  const lines: string[] = []
  const safeTokenSeries = Array.isArray(tokenSeries.value) ? tokenSeries.value : []
  const safeTopErrors = Array.isArray(topErrors.value) ? topErrors.value : []

  if (!safeTokenSeries.length && !safeTopErrors.length) {
    Message.warning('当前筛选范围没有可导出的明细数据')
    return
  }

  lines.push('模块,指标,值')
  lines.push(`范围,当前范围,${scopeLabel.value}`)
  lines.push(`汇总,P95延迟(ms),${summary.value.p95_ms}`)
  lines.push(`汇总,成功率(%),${(summary.value.success_rate * 100).toFixed(2)}`)
  lines.push(`汇总,Token总量,${summary.value.token_total}`)
  lines.push(`汇总,Agent创建量,${summary.value.agent_created}`)
  lines.push(`业务,活跃使用用户(去重),${agentStats.value.used}`)
  lines.push(`业务,7日留存率(%),${(agentStats.value.retention_7d * 100).toFixed(2)}`)

  lines.push('')
  lines.push('Token趋势')
  lines.push('日期,Token,成本')
  safeTokenSeries.forEach((item) => {
    lines.push(
      [escapeCsvValue(item.date), escapeCsvValue(item.tokens), escapeCsvValue(item.cost.toFixed(4))].join(','),
    )
  })

  lines.push('')
  lines.push('错误分布')
  lines.push('错误码,次数')
  safeTopErrors.forEach((item) => {
    lines.push([escapeCsvValue(item.code), escapeCsvValue(item.count)].join(','))
  })

  const bom = '\uFEFF'
  const csvContent = `${bom}${lines.join('\n')}`
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `dashboard_${params.start_date}_${params.end_date}.csv`
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 300)
  Message.success('CSV 导出成功')
}

onMounted(async () => {
  await loadUsers()

  const saved = loadSavedRange()
  if (saved) {
    range.value = saved
    fetchAll()
    return
  }
  applyQuickRange(7)
})
</script>

<template>
  <div class="dashboard-page">
    <section class="hero glass-panel">
      <div>
        <div class="hero-title">品牌运营总览</div>
        <div class="hero-subtitle">从性能、稳定性到业务增长，一屏掌控全局健康度。</div>
      </div>
      <a-tag color="arcoblue" bordered>{{ scopeLabel }}</a-tag>
    </section>

    <a-card class="filters glass-panel" :bordered="false">
      <div class="filters-row">
        <div class="quick-range-buttons force-black-text">
          <a-button
            v-for="item in quickRanges"
            :key="item.value"
            class="quick-range-btn"
            size="small"
            @click="applyQuickRange(item.value)"
          >
            {{ item.label }}
          </a-button>
        </div>

        <template v-if="isAdmin">
          <a-radio-group v-model="scopeMode" type="button" size="small" @change="onScopeChange">
            <a-radio value="all">全量数据</a-radio>
            <a-radio value="user">按用户查看</a-radio>
          </a-radio-group>

          <a-select
            v-if="scopeMode === 'user'"
            v-model="selectedUserId"
            :options="users.map((u) => ({ label: `${u.username} (${u.email})`, value: u.id }))"
            allow-search
            placeholder="选择用户"
            style="width: 280px"
            @change="onTargetUserChange"
          />
        </template>

        <a-range-picker
          v-model="range"
          format="YYYY-MM-DD"
          popup-class-name="dashboard-range-popup"
          @change="onRangeChange"
        />
        <a-button type="outline" size="small" @click="exportCsv">导出 CSV</a-button>
      </div>
    </a-card>

    <a-alert v-if="errorMessage" type="error" :content="errorMessage" closable @close="errorMessage = ''">
      <template #action>
        <a-button type="text" @click="onRetry">重试</a-button>
      </template>
    </a-alert>

    <a-spin :loading="loading" style="width: 100%">
      <a-grid :cols="4" :col-gap="16" :row-gap="16" class="summary-grid">
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic title="P95 延迟" :value="summary.p95_ms" :precision="0" suffix="ms" />
            <div class="delta-text" :class="p95DeltaClass">{{ p95DeltaText }}</div>
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic
              title="成功率"
              :value="summary.success_rate * 100"
              :precision="2"
              suffix="%"
            />
            <div class="delta-text" :class="successRateDeltaClass">{{ successRateDeltaText }}</div>
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic title="Token 总量" :value="summary.token_total" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic title="Agent 创建量" :value="summary.agent_created" :precision="0" />
          </a-card>
        </a-grid-item>
      </a-grid>

      <a-grid :cols="2" :col-gap="16" class="charts-grid">
        <a-grid-item>
          <a-card class="glass-card">
            <VChart v-if="tokenSeries.length" :option="tokenLineOption" autoresize style="height: 360px" />
            <a-empty v-else description="当前时间范围暂无 Token 数据" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <template #title>
              <div class="chart-title-row">
                <span>请求错误分布</span>
                <a-radio-group v-model="errorChartType" type="button" size="small">
                  <a-radio value="pie">饼图</a-radio>
                  <a-radio value="bar">柱状图</a-radio>
                </a-radio-group>
              </div>
            </template>
            <VChart v-if="topErrors.length" :option="errorOption" autoresize style="height: 360px" />
            <a-empty v-else description="当前时间范围无错误请求" />
          </a-card>
        </a-grid-item>
      </a-grid>

      <a-grid :cols="3" :col-gap="16" class="agent-metrics-grid">
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic title="活跃使用用户(去重)" :value="agentStats.used" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic title="创建 Agent 数" :value="agentStats.created" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="glass-card">
            <a-statistic
              title="7日留存率"
              :value="agentStats.retention_7d * 100"
              :precision="2"
              suffix="%"
            />
          </a-card>
        </a-grid-item>
      </a-grid>
    </a-spin>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.glass-panel {
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
  border-radius: var(--radius-xl);
}

.hero {
  padding: 20px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background-image: linear-gradient(135deg, rgba(109, 94, 248, 0.24), rgba(79, 140, 255, 0.16));
}

.hero-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-1);
}

.hero-subtitle {
  margin-top: 6px;
  color: var(--text-2);
  font-size: 13px;
}

.filters {
  background: rgba(18, 28, 56, 0.7);
}

.filters-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quick-range-buttons {
  display: flex;
  gap: 8px;
}

.force-black-text,
.force-black-text :deep(*),
.force-black-text :deep(.arco-btn),
.force-black-text :deep(.arco-btn-content) {
  color: #111827 !important;
}

.chart-title-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.glass-card {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
}

.summary-grid,
.charts-grid,
.agent-metrics-grid {
  margin-top: 12px;
}

.delta-text {
  margin-top: 8px;
  font-size: 12px;
}

.delta-up {
  color: #27d3c3;
}

.delta-down {
  color: #ff5d73;
}

.delta-neutral {
  color: var(--text-3);
}

/* 指定区域：文字改为黑色（按截图框选控件） */
:deep(.hero .arco-tag),
:deep(.filters-row .arco-btn),
:deep(.filters-row .arco-btn .arco-btn-content),
:deep(.filters-row .arco-radio-button),
:deep(.filters-row .arco-radio-label),
:deep(.filters-row .arco-select-view-value),
:deep(.filters-row .arco-picker),
:deep(.filters-row .arco-picker input),
:deep(.chart-title-row .arco-radio-button),
:deep(.chart-title-row .arco-radio-label) {
  color: #111827 !important;
}

:deep(.filters-row .arco-btn),
:deep(.filters-row .arco-radio-button),
:deep(.filters-row .arco-radio-button .arco-radio-button-content),
:deep(.filters-row .arco-radio-button .arco-radio-label),
:deep(.filters-row .arco-radio-button.arco-radio-checked),
:deep(.filters-row .arco-radio-button.arco-radio-checked .arco-radio-button-content),
:deep(.filters-row .arco-radio-button.arco-radio-checked .arco-radio-label),
:deep(.filters-row .arco-select-view),
:deep(.filters-row .arco-picker),
:deep(.hero .arco-tag),
:deep(.chart-title-row .arco-radio-button),
:deep(.chart-title-row .arco-radio-button .arco-radio-button-content),
:deep(.chart-title-row .arco-radio-button .arco-radio-label),
:deep(.chart-title-row .arco-radio-button.arco-radio-checked),
:deep(.chart-title-row .arco-radio-button.arco-radio-checked .arco-radio-button-content),
:deep(.chart-title-row .arco-radio-button.arco-radio-checked .arco-radio-label) {
  background: rgba(255, 255, 255, 0.95) !important;
  border-color: rgba(0, 0, 0, 0.38) !important;
  color: #111827 !important;
}

/* 快捷范围按钮（你最新截图这一块） */
.quick-range-btn,
.quick-range-btn :deep(*) {
  color: #111827 !important;
}

.quick-range-btn:deep(.arco-btn),
.quick-range-btn:deep(.arco-btn-content),
:deep(.quick-range-btn.arco-btn),
:deep(.quick-range-btn .arco-btn-content) {
  color: #111827 !important;
  background: rgba(255, 255, 255, 0.96) !important;
  border-color: rgba(0, 0, 0, 0.45) !important;
}

:deep(.quick-range-btn.arco-btn:hover),
:deep(.quick-range-btn.arco-btn:focus),
:deep(.quick-range-btn.arco-btn:active) {
  color: #111827 !important;
  background: #ffffff !important;
  border-color: rgba(0, 0, 0, 0.65) !important;
}

/* 日期范围输入框（你截图第一个红框） */
:deep(.filters-row .arco-picker input),
:deep(.filters-row .arco-picker input::placeholder),
:deep(.filters-row .arco-picker .arco-picker-suffix-icon),
:deep(.filters-row .arco-picker .arco-picker-clear-icon) {
  color: #111827 !important;
}

/* 错误分布切换按钮（你截图第二个红框） */
:deep(.chart-title-row .arco-radio-button),
:deep(.chart-title-row .arco-radio-button *),
:deep(.chart-title-row .arco-radio),
:deep(.chart-title-row .arco-radio *) {
  color: #111827 !important;
}

:deep(.chart-title-row .arco-radio-button.arco-radio-checked) {
  background: #ffffff !important;
  border-color: rgba(0, 0, 0, 0.45) !important;
}

/* 日期弹层（红框区域）文字改为黑色
   注意：弹层挂载在 body（teleport），scoped + deep 选不中，所以改用 :global */
:global(.dashboard-range-popup),
:global(.dashboard-range-popup *),
:global(.dashboard-range-popup .arco-picker-date-value),
:global(.dashboard-range-popup .arco-picker-cell),
:global(.dashboard-range-popup .arco-picker-header-title),
:global(.dashboard-range-popup .arco-picker-header-label),
:global(.dashboard-range-popup .arco-picker-week-list-item),
:global(.dashboard-range-popup .arco-picker-cell-in-view .arco-picker-date-value),
:global(.dashboard-range-popup .arco-picker-cell-in-range .arco-picker-date-value),
:global(.dashboard-range-popup .arco-picker-cell-selected .arco-picker-date-value) {
  color: #111827 !important;
}
</style>
