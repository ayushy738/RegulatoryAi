"use client";

/**
 * Skeletons mirror the layout they replace so content arrival does not shift the
 * page. Used for first loads; in-place refetches keep the previous content.
 */
export function Skeleton({
  width = "100%",
  height = 14,
  radius,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number;
}) {
  return (
    <span
      className="rv-skeleton"
      aria-hidden
      style={{
        display: "block",
        width,
        height,
        borderRadius: radius,
      }}
    />
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rv-skeleton-stack" aria-hidden>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} width={index === lines - 1 ? "60%" : "100%"} />
      ))}
    </div>
  );
}

/** Card-shaped placeholders for list and feed layouts. */
export function SkeletonCards({
  count = 3,
  lines = 3,
  label = "Loading",
}: {
  count?: number;
  lines?: number;
  label?: string;
}) {
  return (
    <div className="rv-skeleton-stack" role="status" aria-live="polite" aria-busy="true">
      <span className="rv-visually-hidden">{label}</span>
      {Array.from({ length: count }, (_, index) => (
        <div className="rv-skeleton-card" key={index}>
          <Skeleton width="35%" height={16} />
          <SkeletonText lines={lines} />
        </div>
      ))}
    </div>
  );
}

/** Table-shaped placeholder matching the eventual column count. */
export function SkeletonTable({
  rows = 6,
  columns = 5,
  label = "Loading rows",
}: {
  rows?: number;
  columns?: number;
  label?: string;
}) {
  return (
    <div
      className="rv-table-wrap"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span className="rv-visually-hidden">{label}</span>
      <div style={{ padding: 16, display: "grid", gap: 14 }}>
        {Array.from({ length: rows }, (_, rowIndex) => (
          <div
            key={rowIndex}
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${columns}, 1fr)`,
              gap: 16,
            }}
          >
            {Array.from({ length: columns }, (_, columnIndex) => (
              <Skeleton
                key={columnIndex}
                width={columnIndex === 0 ? "80%" : "55%"}
                height={12}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonMetrics({ count = 5 }: { count?: number }) {
  return (
    <section className="rv-metrics" aria-busy="true" aria-label="Loading metrics">
      {Array.from({ length: count }, (_, index) => (
        <div className="rv-metric" key={index}>
          <Skeleton width="50%" height={11} />
          <Skeleton width="35%" height={22} />
        </div>
      ))}
    </section>
  );
}
