import Plot from 'react-plotly.js'

interface BarChartData {
  x: string[]
  y: number[]
}

interface NeonBarChartProps {
  data: BarChartData
  title: string
  orientation?: 'v' | 'h'
  height?: number
  color?: string
}

export default function NeonBarChart({ 
  data, 
  title, 
  orientation = 'v',
  height = 350,
  color = '#00ffcc'
}: NeonBarChartProps) {
  return (
    <Plot
      data={[{
        type: 'bar',
        x: orientation === 'v' ? data.x : data.y,
        y: orientation === 'v' ? data.y : data.x,
        orientation,
        marker: {
          color,
          line: { color: color, width: 1 }
        },
        hovertemplate: orientation === 'v' 
          ? '<b>%{x}</b><br>%{y:.2f}h<extra></extra>'
          : '<b>%{y}</b><br>%{x:.2f}h<extra></extra>'
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
        margin: { t: 50, r: 30, l: 60, b: 60 },
        xaxis: {
          gridcolor: 'rgba(255,255,255,0.1)',
          zerolinecolor: 'rgba(255,255,255,0.2)'
        },
        yaxis: {
          gridcolor: 'rgba(255,255,255,0.1)',
          zerolinecolor: 'rgba(255,255,255,0.2)'
        },
        bargap: 0.2
      }}
      config={{ displayModeBar: false }}
    />
  )
}
