/**
 * Minimal dependency-free sparkline. The project has no charting library
 * installed (verified in package.json) and this sandbox has no network
 * access to add one safely, so this renders a smoothed line + soft area
 * fill directly as SVG from a plain number array.
 */
export function Sparkline({
  values,
  width = 480,
  height = 120,
  strokeClassName = "stroke-gold",
  fillId,
}: {
  values: number[];
  width?: number;
  height?: number;
  strokeClassName?: string;
  fillId: string;
}) {
  if (values.length < 2) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-xs">
        Not enough data yet
      </div>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 8;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - pad * 2) + pad;
    const y = height - pad - ((v - min) / range) * (height - pad * 2);
    return [x, y] as const;
  });

  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1]![0].toFixed(1)},${height} L${points[0]![0].toFixed(1)},${height} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${fillId})`} />
      <path d={linePath} fill="none" className={strokeClassName} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
