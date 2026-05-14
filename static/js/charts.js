/* 本棚 - ECharts 图表渲染 (日系柔色主题) */

// 柔色调色板
const PALETTE = {
  matcha:  '#A8C8B8',  // 柔雾绿
  sakura:  '#E8B4A0',  // 樱花粉
  sky:     '#C4D5E0',  // 淡蓝
  warm:    '#8A8680',  // 暖灰
  cream:   '#F5F1E8',  // 奶油
  ink:     '#3D3D3D',  // 炭灰
  border:  '#E5E0D5',  // 米边
};

const CHART_COLORS = [
  PALETTE.matcha,
  PALETTE.sakura,
  PALETTE.sky,
  PALETTE.warm,
];

const BASE_TEXT_STYLE = {
  fontFamily: '"Noto Sans SC", ui-sans-serif, sans-serif',
  color: PALETTE.ink,
  fontSize: 12,
};

function baseOption() {
  return {
    textStyle: BASE_TEXT_STYLE,
    backgroundColor: 'transparent',
    grid: { left: 40, right: 20, top: 30, bottom: 30, containLabel: true },
    tooltip: {
      backgroundColor: '#FFFFFF',
      borderColor: PALETTE.border,
      borderWidth: 1,
      textStyle: BASE_TEXT_STYLE,
      padding: [8, 12],
    },
  };
}

/* 状态占比 - 环形图 */
function renderStatusChart(el, data) {
  const chart = echarts.init(el);
  chart.setOption({
    ...baseOption(),
    color: [PALETTE.warm, PALETTE.matcha, PALETTE.sakura],
    tooltip: { trigger: 'item', ...baseOption().tooltip },
    legend: {
      bottom: 0,
      itemGap: 16,
      icon: 'circle',
      textStyle: { ...BASE_TEXT_STYLE, color: PALETTE.warm },
    },
    series: [{
      type: 'pie',
      radius: ['50%', '72%'],
      center: ['50%', '46%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#FAF8F3', borderWidth: 3, borderRadius: 4 },
      label: { show: true, formatter: '{b}\n{d}%', color: PALETTE.ink, fontSize: 11 },
      labelLine: { length: 8, length2: 12, smooth: true, lineStyle: { color: PALETTE.border } },
      data: data,
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}

/* 年度阅读 - 柱图 */
function renderYearlyChart(el, years, counts) {
  const chart = echarts.init(el);
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, ...baseOption().tooltip },
    xAxis: {
      type: 'category',
      data: years,
      axisLine: { lineStyle: { color: PALETTE.border } },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: PALETTE.border, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm },
    },
    series: [{
      type: 'bar',
      data: counts,
      barMaxWidth: 36,
      itemStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: PALETTE.matcha },
            { offset: 1, color: 'rgba(168, 200, 184, 0.4)' },
          ],
        },
        borderRadius: [4, 4, 0, 0],
      },
      label: { show: true, position: 'top', color: PALETTE.warm, fontSize: 11 },
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}

/* 标签 Top 10 - 横向条形图 */
function renderTagsChart(el, names, counts) {
  const chart = echarts.init(el);
  chart.setOption({
    ...baseOption(),
    grid: { left: 80, right: 40, top: 10, bottom: 20, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, ...baseOption().tooltip },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: PALETTE.border, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm },
    },
    yAxis: {
      type: 'category',
      data: names.slice().reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.ink },
    },
    series: [{
      type: 'bar',
      data: counts.slice().reverse(),
      barMaxWidth: 18,
      itemStyle: {
        color: PALETTE.sky,
        borderRadius: [0, 4, 4, 0],
      },
      label: { show: true, position: 'right', color: PALETTE.warm, fontSize: 11 },
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}

/* 评分分布 - 柱图 */
function renderRatingChart(el, labels, counts) {
  const chart = echarts.init(el);
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, ...baseOption().tooltip },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: PALETTE.border } },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: PALETTE.border, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm },
    },
    series: [{
      type: 'bar',
      data: counts,
      barMaxWidth: 36,
      itemStyle: {
        color: PALETTE.sakura,
        borderRadius: [4, 4, 0, 0],
      },
      label: { show: true, position: 'top', color: PALETTE.warm, fontSize: 11 },
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}

/* 阅读时长排行 - 横向条形图 */
function renderReadingTimeChart(el, names, hours) {
  const chart = echarts.init(el);
  chart.setOption({
    ...baseOption(),
    grid: { left: 80, right: 40, top: 10, bottom: 20, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...baseOption().tooltip,
      formatter: function (params) {
        return params[0].name + ': ' + params[0].value + ' 小时';
      }
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: PALETTE.border, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.warm, formatter: '{value}h' },
    },
    yAxis: {
      type: 'category',
      data: names.slice().reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.ink, width: 70, overflow: 'truncate' },
    },
    series: [{
      type: 'bar',
      data: hours.slice().reverse(),
      barMaxWidth: 18,
      itemStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [
            { offset: 0, color: 'rgba(168, 200, 184, 0.5)' },
            { offset: 1, color: PALETTE.matcha },
          ],
        },
        borderRadius: [0, 4, 4, 0],
      },
      label: { show: true, position: 'right', color: PALETTE.warm, fontSize: 11, formatter: '{c}h' },
    }],
  });
  window.addEventListener('resize', () => chart.resize());
}

// 暴露到 window
window.BookCharts = {
  renderStatusChart,
  renderYearlyChart,
  renderTagsChart,
  renderRatingChart,
  renderReadingTimeChart,
};
