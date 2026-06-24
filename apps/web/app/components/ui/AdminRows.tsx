import type { ReactNode } from "react";

import { EmptyState } from "./EmptyState";

export function AdminRows<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: Array<[string, (row: T) => ReactNode]>;
}) {
  if (!rows.length) {
    return <EmptyState title="No rows" body="No records are available for this admin view." />;
  }
  return (
    <div className="admin-table">
      <div
        className="admin-table-head"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(120px, 1fr))` }}
      >
        {columns.map(([label]) => (
          <strong key={label}>{label}</strong>
        ))}
      </div>
      {rows.map((row, rowIndex) => (
        <div
          className="admin-table-row"
          key={rowIndex}
          style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(120px, 1fr))` }}
        >
          {columns.map(([label, render]) => (
            <div key={label}>{render(row)}</div>
          ))}
        </div>
      ))}
    </div>
  );
}
