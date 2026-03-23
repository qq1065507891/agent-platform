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
import {
  getMetricsAgents,
  getMetricsErrors,
  getMetricsSummary,
  getMetricsTokens,
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

const loading = ref(false)
const range = ref<string[]>([])
const errorMessage = ref('')
const errorChartType = ref<'pie' | 'bar'>('pie')

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

const fetchAll = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const params = getRangeParams()
    const previousParams = getPreviousRangeParams(params)

    const [summaryData, errorsData, tokensData, agentsData, previousSummaryData] = await Promise.all([
      getMetricsSummary(params),
      getMetricsErrors(params),
      getMetricsTokens(params),
      getMetricsAgents(params),
      previousParams ? getMetricsSummary(previousParams) : Promise.resolve(null),
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
  title: { text: '每日 Token 消耗趋势' },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: tokenSeries.value.map((item) => item.date),
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'line',
      smooth: true,
      data: tokenSeries.value.map((item) => item.tokens),
      areaStyle: {},
    },
  ],
}))

const errorOption = computed(() => {
  if (errorChartType.value === 'bar') {
    return {
      title: { text: '请求错误分布（柱状图）' },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: topErrors.value.map((item) => `${item.code}`),
      },
      yAxis: { type: 'value' },
      series: [
        {
          type: 'bar',
          data: topErrors.value.map((item) => item.count),
          barWidth: 24,
        },
      ],
    }
  }

  return {
    title: { text: '请求错误分布（饼图）' },
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
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

onMounted(() => {
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
    <a-card class="filters" :bordered="false">
      <div class="filters-row">
        <div class="quick-range-buttons">
          <a-button
            v-for="item in quickRanges"
            :key="item.value"
            size="small"
            @click="applyQuickRange(item.value)"
          >
            {{ item.label }}
          </a-button>
        </div>
        <a-range-picker v-model="range" format="YYYY-MM-DD" @change="onRangeChange" />
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
          <a-card>
            <a-statistic title="P95 延迟" :value="summary.p95_ms" :precision="0" suffix="ms" />
            <div class="delta-text" :class="p95DeltaClass">{{ p95DeltaText }}</div>
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card>
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
          <a-card>
            <a-statistic title="Token 总量" :value="summary.token_total" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card>
            <a-statistic title="Agent 创建量" :value="summary.agent_created" :precision="0" />
          </a-card>
        </a-grid-item>
      </a-grid>

      <a-grid :cols="2" :col-gap="16" class="charts-grid">
        <a-grid-item>
          <a-card>
            <VChart v-if="tokenSeries.length" :option="tokenLineOption" autoresize style="height: 360px" />
            <a-empty v-else description="当前时间范围暂无 Token 数据" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card>
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
          <a-card>
            <a-statistic title="活跃使用用户(去重)" :value="agentStats.used" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card>
            <a-statistic title="创建 Agent 数" :value="agentStats.created" :precision="0" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card>
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

.filters-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}

.quick-range-buttons {
  display: flex;
  gap: 8px;
}

.chart-title-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  color: rgb(var(--success-6));
}

.delta-down {
  color: rgb(var(--danger-6));
}

.delta-neutral {
  color: rgb(var(--gray-6));
}
</style>
