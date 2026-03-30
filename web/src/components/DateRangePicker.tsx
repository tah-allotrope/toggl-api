import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'

interface DateRangePickerProps {
  startDate: Date | null
  endDate: Date | null
  onChange: (start: Date | null, end: Date | null) => void
}

export default function DateRangePicker({ startDate, endDate, onChange }: DateRangePickerProps) {
  return (
    <div className="date-range-inputs">
      <DatePicker
        selected={startDate}
        onChange={(dates) => {
          const [start, end] = dates as [Date | null, Date | null]
          onChange(start, end)
        }}
        startDate={startDate}
        endDate={endDate}
        selectsRange
        placeholderText="Select date range"
        dateFormat="yyyy-MM-dd"
        className="date-input"
      />
    </div>
  )
}
