"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "./Button";

export type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  /** Plural noun for the status line, e.g. "sources". */
  itemLabel: string;
  busy?: boolean;
};

/**
 * Server-side pagination control. Renders nothing when a single page holds the
 * whole result set, so short lists are not decorated with dead controls.
 */
export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  itemLabel,
  busy = false,
}: PaginationProps) {
  if (total === 0) return null;

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const hasPrevious = page > 1;
  const hasNext = page < totalPages;

  if (!hasPrevious && !hasNext) {
    return (
      <div className="rv-pagination">
        <p className="rv-pagination__status">
          {total} {itemLabel}
        </p>
      </div>
    );
  }

  return (
    <nav className="rv-pagination" aria-label={`${itemLabel} pagination`}>
      <p className="rv-pagination__status" aria-live="polite">
        Showing {first}–{last} of {total} {itemLabel}
      </p>
      <div className="rv-pagination__controls">
        <Button
          variant="secondary"
          size="sm"
          Icon={ChevronLeft}
          disabled={!hasPrevious || busy}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <span className="rv-pagination__page">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="secondary"
          size="sm"
          Icon={ChevronRight}
          iconPosition="end"
          disabled={!hasNext || busy}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
