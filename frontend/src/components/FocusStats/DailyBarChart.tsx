import "./DailyBarChart.css";

// Simple CSS bar chart -- one series, no need for a charting library
// dependency here (personal tool, single hue, no legend needed; see
// app.py's comment above its own st.bar_chart(daily_minutes) call, which
// this replicates 1:1 in shape). `dailyMinutes` keys arrive from
// GET /api/sessions/stats already ordered oldest -> newest (the backend
// builds the dict in that order and JSON preserves string-key insertion
// order), so this renders them as received without re-sorting.

interface DailyBarChartProps {
  dailyMinutes: Record<string, number>;
}

export function DailyBarChart({ dailyMinutes }: DailyBarChartProps) {
  const entries = Object.entries(dailyMinutes);
  const max = Math.max(1, ...entries.map(([, minutes]) => minutes));

  return (
    <div
      className="daily-bar-chart"
      role="img"
      aria-label={`Daily focused minutes: ${entries
        .map(([day, minutes]) => `${day} ${minutes.toFixed(0)} minutes`)
        .join(", ")}`}
    >
      {entries.map(([day, minutes]) => (
        <div key={day} className="daily-bar-chart__col">
          <div className="daily-bar-chart__track">
            <div
              className="daily-bar-chart__bar"
              style={{ height: `${Math.max(2, (minutes / max) * 100)}%` }}
              title={`${day}: ${minutes.toFixed(0)} min`}
            />
          </div>
          <span className="daily-bar-chart__label">{day}</span>
        </div>
      ))}
    </div>
  );
}

export default DailyBarChart;
