/** Reusable loading skeleton primitives for the dashboard. */

export function SkeletonLine({ width = "100%", height = "h-3" }) {
  return (
    <div
      className={`${height} rounded-md bg-slate-800 animate-pulse`}
      style={{ width }}
      data-testid="skeleton-line"
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 space-y-3" data-testid="skeleton-card">
      <SkeletonLine width="40%" height="h-4" />
      <SkeletonLine width="80%" />
      <SkeletonLine width="60%" />
    </div>
  );
}

export function SkeletonGrid({ cols = 4, rows = 3 }) {
  return (
    <div className={`grid gap-2`} style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }} data-testid="skeleton-grid">
      {Array.from({ length: cols * rows }).map((_, i) => (
        <div key={i} className="rounded-lg bg-slate-800 animate-pulse h-16" />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="rounded-lg border border-slate-700 overflow-hidden" data-testid="skeleton-table">
      <div className="bg-slate-800/80 p-2 flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonLine key={i} width={`${20 + Math.random() * 20}%`} height="h-3" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="p-2 flex gap-4 border-t border-slate-800/50">
          {Array.from({ length: cols }).map((_, j) => (
            <SkeletonLine key={j} width={`${30 + Math.random() * 30}%`} height="h-2.5" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function HeatmapSkeleton() {
  return (
    <div className="space-y-3" data-testid="heatmap-skeleton">
      <div className="flex items-center gap-3">
        <SkeletonLine width="160px" height="h-5" />
        <SkeletonLine width="80px" height="h-6" />
        <SkeletonLine width="80px" height="h-6" />
        <SkeletonLine width="80px" height="h-6" />
      </div>
      <SkeletonGrid cols={6} rows={3} />
    </div>
  );
}
