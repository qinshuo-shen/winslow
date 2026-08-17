import "./DailyBarChart.css";

// Simple CSS bar chart -- one series, no need for a charting library
// dependency here (personal tool, single hue, no legend needed; see
// app.py's comment above its own st.bar_chart(daily_minutes) call, which
// this replicates 1:1 in shape). `dailyMinutes` keys arrive from
// GET /api/sessions/stats already ordered oldest -> newest (the backend
// builds the dict in that order and JSON preserves string-key insertion
// order), so this renders them as received without re-sorting.
//
// Hour y-axis (follow-up): the axis column mirrors the day columns'
// flex layout exactly (a flex:1 track + a same-height spacer standing in
// for the day-label row below it) purely so its tick positions land in the
// same coordinate space as the bars, without needing to know the track's
// actual pixel height -- flexbox does that alignment for free as long as
// both sides use the same flex ratios.

interface DailyBarChartProps {
  dailyMinutes: Record<string, number>;
}

export function DailyBarChart({ dailyMinutes }: DailyBarChartProps) {
  const entries = Object.entries(dailyMinutes);
  const maxMinutesInWindow = Math.max(1, ...entries.map(([, minutes]) => minutes));

  // Bars scale against the y-axis's own top (a whole number of hours, at
  // least 1h) rather than directly against maxMinutesInWindow -- so the
  // tallest bar lines up with where it actually falls on the labeled scale
  // instead of always touching the top of the chart regardless of how much
  // time that represents.
  const axisMaxHours = Math.max(1, Math.ceil(maxMinutesInWindow / 60));
  const axisMaxMinutes = axisMaxHours * 60;
  const tickStep = axisMaxHours <= 5 ? 1 : Math.ceil(axisMaxHours / 5);
  const ticks: number[] = [];
  for (let h = 0; h <= axisMaxHours; h += tickStep) ticks.push(h);
  if (ticks[ticks.length - 1] !== axisMaxHours) ticks.push(axisMaxHours);

  return (
    <div className="daily-bar-chart-row">
      <div className="daily-bar-chart__axis-col" aria-hidden="true">
        <div className="daily-bar-chart__axis-track">
          {ticks.map((h) => (
            <span
              key={h}
              className="daily-bar-chart__axis-tick"
              style={{ bottom: `${(h / axisMaxHours) * 100}%` }}
            >
              {h}h
            </span>
          ))}
        </div>
        <span className="daily-bar-chart__axis-spacer" />
      </div>

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
                style={{ height: `${Math.max(2, (minutes / axisMaxMinutes) * 100)}%` }}
                title={`${day}: ${minutes.toFixed(0)} min`}
              />
            </div>
            <span className="daily-bar-chart__label">{day}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default DailyBarChart;
