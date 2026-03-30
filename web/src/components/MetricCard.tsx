interface MetricCardProps {
  value: string | number
  label: string
}

export default function MetricCard({ value, label }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}
