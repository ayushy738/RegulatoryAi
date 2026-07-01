import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { EmptyState } from "./EmptyState";

const PAGE_SIZE = 20;

function cellText(value: ReactNode) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "";
}

function rowText(row: unknown) {
  try {
    return JSON.stringify(row).toLowerCase();
  } catch {
    return "";
  }
}

export function AdminRows<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: Array<[string, (row: T) => ReactNode]>;
}) {
  const [search, setSearch] = useState("");
  const [sortIndex, setSortIndex] = useState(0);
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(0);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => rowText(row).includes(q));
  }, [rows, search]);

  const sortedRows = useMemo(() => {
    const next = [...filteredRows];
    const render = columns[sortIndex]?.[1];
    if (!render) return next;
    next.sort((a, b) => {
      const left = cellText(render(a)).toLowerCase();
      const right = cellText(render(b)).toLowerCase();
      return sortAsc ? left.localeCompare(right) : right.localeCompare(left);
    });
    return next;
  }, [columns, filteredRows, sortAsc, sortIndex]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const pageRows = sortedRows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  if (!rows.length) {
    return <EmptyState title="No rows" body="No records are available for this admin view." />;
  }
  return (
    <div className="admin-table-wrap">
      <div className="admin-table-toolbar">
        <label className="search-box">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            placeholder="Search table"
          />
        </label>
        <span>
          Showing {pageRows.length} of {filteredRows.length} rows
        </span>
      </div>
      <div className="admin-table">
        <div
          className="admin-table-head"
          style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(120px, 1fr))` }}
        >
          {columns.map(([label], index) => (
            <button
              type="button"
              key={label}
              onClick={() => {
                if (sortIndex === index) {
                  setSortAsc(!sortAsc);
                } else {
                  setSortIndex(index);
                  setSortAsc(true);
                }
              }}
            >
              {label}
              {sortIndex === index ? (sortAsc ? " ↑" : " ↓") : ""}
            </button>
          ))}
        </div>
        {pageRows.map((row, rowIndex) => (
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
      <div className="admin-pagination">
        <button type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>
          <ChevronLeft size={16} />
          Previous
        </button>
        <span>
          Page {page + 1} of {pageCount}
        </span>
        <button
          type="button"
          disabled={page >= pageCount - 1}
          onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
        >
          Next
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
