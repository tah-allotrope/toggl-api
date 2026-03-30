import Plot from 'react-plotly.js'

interface PieChartData {
  labels: string[]
  values: number[]
}

interface NeonPieChartProps {
  data: PieChartData
  title: string
  height?: number
}

const CHART_COLORS = [
  '#00ffcc', '#ff00ff', '#ffff00', '#ff6600', '#9966ff',
  '#ff6699', '#33ff99', '#3399ff', '#ff3333', '#ccff00'
]

export default function NeonPieChart({ data, title, height = 350 }: NeonPieChartProps) {
  return (
    <Plot
      data={[{
        type: 'pie',
        labels: data.labels,
        values: data.values,
        textinfo: 'label+percent',
        textposition: 'outside',
        automargin: true,
        marker: {
          colors: CHART_COLORS.slice(0, data.labels.length)
        },
        hovertemplate: '<b>%{label}</b><br>%{percent}<extra></extra>'
      }]}
      layout={{
        title: {
          text: title,
          font: { color: '#00ffcc', size: 16 }
        },
        height,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#e0e0e0' },
        margin: { t: 50, r: 30, l: 30, b: 30 },
        showlegend: false
      }}
      config={{ displayModeBar: false }}
    />
  )
}
