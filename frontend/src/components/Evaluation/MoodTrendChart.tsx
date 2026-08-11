import "./MoodTrendChart.css";

// Same hand-rolled-CSS-bar approach as FocusStats/DailyBarChart.tsx --
// no charting library dependency for a single-series, single-hue chart.
// `entries` arrives oldest -> newest (Evaluation.tsx reverses the
// most-recent-first history fetch before passing it in here).

interface MoodTrendChartProps {
  entries: { date: string; moodAvg: number | null }[];
}

export function MoodTrendChart({ entries }: MoodTrendChartProps) {
  return (
    <div
      className="mood-trend-chart"
      role="img"
      aria-label={`Mood trend: ${entries
        .map((e) => `${e.date} ${e.moodAvg === null ? "no entry" : e.moodAvg.toFixed(1)}`)
        .join(", ")}`}
    >
      {entries.map((e) => (
        <div key={e.date} className="mood-trend-chart__col">
          <div className="mood-trend-chart__track">
            {e.moodAvg !== null && (
              <div
                className="mood-trend-chart__bar"
                style={{ height: `${Math.max(4, (e.moodAvg / 5) * 100)}%` }}
                title={`${e.date}: ${e.moodAvg.toFixed(1)}/5`}
              />
            )}
          </div>
          <span className="mood-trend-chart__label">{e.date.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

export default MoodTrendChart;
