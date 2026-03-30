import Plot from 'react-plotly.js'

interface HeatmapData {
  date: string
  hours: number
}

interface NeonHeatmapProps {
  data: HeatmapData[]
  title: string
  height?: number
}

export default function NeonHeatmap({ data, title, height = 200 }: NeonHeatmapProps) {
  const dates = data.map(d => d.date)
  const hours = data.map(d => d.hours)
  
  const colorscale = [
    [0, 'rgba(0, 255, 204, 0.1)'],
    [0.25, 'rgba(0, 255, 204, 0.3)'],
    [0.5, 'rgba(0, 255, 204, 0.5)'],
    [0.75, 'rgba(0, 255, 204, 0.7)'],
    [1, '#00ffcc']
  ]

  return (
    <Plot
      data={[{
        type: 'histogram2dcontour',
        x: dates,
        y: hours.map(() => 'Hours'),
        ncontours: 5,
        colorscale,
        showscale: true,
        colorbar: {
          title: 'Hours',
          titleside: 'right',
          titlefont: { color: '#e0e0e0' },
          tickfont: { color: '#e0e0e0' }
        },
        hovertemplate: '<b>%{x}</b><br>%{y}: %{z:.2f}h<extra></extra>'
      }]}
      layout={{
        title: {
          text: title,
          font: { color: '#00ffcc', size: 16 }
        },
        height,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#e0e0e0', size: 10 },
        margin: { t: 50, r: 60, l: 50, b: 40 },
        xaxis: {
          gridcolor: 'rgba(255,255,255,0.1)',
          tickangle: -45,
          tickfont: { size: 9 }
        },
        yaxis: {
          showticklabels: false,
          gridcolor: 'rgba(255,255,255,0.1)'
        }
      }}
      config={{ displayModeBar: false }}
    />
  )
}
