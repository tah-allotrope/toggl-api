import Plot from 'react-plotly.js'

interface LineChartData {
  x: (string | number)[]
  y: number[]
  name?: string
}

interface NeonLineChartProps {
  data: LineChartData | LineChartData[]
  title: string
  height?: number
  showArea?: boolean
}

export default function NeonLineChart({ 
  data, 
  title, 
  height = 350,
  showArea = false
}: NeonLineChartProps) {
  const dataArray = Array.isArray(data) ? data : [data]
  
  const traces = dataArray.map((d, idx) => ({
    type: 'scatter',
    mode: 'lines+markers' as const,
    x: d.x,
    y: d.y,
    name: d.name,
    fill: showArea ? 'tozeroy' : undefined,
    marker: { 
      color: idx === 0 ? '#00ffcc' : '#ff00ff',
      size: 6
    },
    line: {
      color: idx === 0 ? '#00ffcc' : '#ff00ff',
      width: 2
    },
    hovertemplate: '<b>%{x}</b><br>%{y:.2f}h<extra></extra>'
  }))

  return (
    <Plot
      data={traces}
      layout={{
        title: {
          text: title,
          font: { color: '#00ffcc', size: 16 }
        },
        height,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#e0e0e0' },
        margin: { t: 50, r: 30, l: 50, b: 50 },
        xaxis: {
          gridcolor: 'rgba(255,255,255,0.1)',
          zerolinecolor: 'rgba(255,255,255,0.2)'
        },
        yaxis: {
          gridcolor: 'rgba(255,255,255,0.1)',
          zerolinecolor: 'rgba(255,255,255,0.2)'
        },
        showlegend: dataArray.length > 1,
        legend: {
          x: 1,
          xanchor: 'right' as const,
          y: 1
        }
      }}
      config={{ displayModeBar: false }}
    />
  )
}
