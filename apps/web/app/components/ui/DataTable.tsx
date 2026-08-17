"use client";

import type { ReactNode } from "react";

export type DataColumn<T> = {
  id: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Right-aligned, tabular figures. */
  numeric?: boolean;
  /** Actions column: shrink to content and never render on the mobile card. */
  actions?: boolean;
  /** Omit from the mobile card representation. */
  hideOnMobile?: boolean;
  /** Promote to the mobile card title row instead of the field grid. */
  mobilePrimary?: boolean;
};

export type DataTableProps<T> = {
  caption: string;
  columns: Array<DataColumn<T>>;
  rows: T[];
  rowKey: (row: T) => string | number;
  /** Makes the whole row activatable by click, Enter and Space. */
  onRowActivate?: (row: T) => void;
  /** Accessible description of what activating a row does. */
  rowActionLabel?: (row: T) => string;
  /** Rendered inside the mobile card footer. */
  mobileActions?: (row: T) => ReactNode;
};

/**
 * One row model, two presentations. Above 768px it is a real `<table>`; below,
 * the same rows render as cards so wide operational tables stay usable at
 * 360px without horizontal scrolling.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  onRowActivate,
  rowActionLabel,
  mobileActions,
}: DataTableProps<T>) {
  const primaryColumn = columns.find((column) => column.mobilePrimary) ?? columns[0];
  const cardFields = columns.filter(
    (column) =>
      column !== primaryColumn && !column.actions && !column.hideOnMobile,
  );

  return (
    <>
      <div className="rv-table-wrap">
        <div className="rv-table-scroll">
          <table className="rv-table">
            <caption className="rv-visually-hidden">{caption}</caption>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.id}
                    scope="col"
                    className={[
                      column.numeric ? "rv-table__numeric" : "",
                      column.actions ? "rv-table__actions" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {column.actions ? (
                      <span className="rv-visually-hidden">{column.header}</span>
                    ) : (
                      column.header
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={onRowActivate ? "rv-row--clickable" : undefined}
                  tabIndex={onRowActivate ? 0 : undefined}
                  aria-label={rowActionLabel?.(row)}
                  onClick={
                    onRowActivate
                      ? (event) => {
                          // Let nested controls handle their own clicks.
                          if (
                            (event.target as HTMLElement).closest(
                              "button, a, select, input",
                            )
                          ) {
                            return;
                          }
                          onRowActivate(row);
                        }
                      : undefined
                  }
                  onKeyDown={
                    onRowActivate
                      ? (event) => {
                          if (event.target !== event.currentTarget) return;
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onRowActivate(row);
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((column) => (
                    <td
                      key={column.id}
                      className={[
                        column.numeric ? "rv-table__numeric" : "",
                        column.actions ? "rv-table__actions" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ul className="rv-record-list" aria-label={caption}>
        {rows.map((row) => (
          <li className="rv-record" key={rowKey(row)}>
            <div className="rv-record__header">
              <div style={{ minWidth: 0 }}>{primaryColumn?.render(row)}</div>
            </div>
            {cardFields.length ? (
              <dl className="rv-record__fields">
                {cardFields.map((column) => (
                  <div className="rv-fact" key={column.id}>
                    <dt className="rv-fact__label">{column.header}</dt>
                    <dd className="rv-fact__value" style={{ margin: 0 }}>
                      {column.render(row)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {mobileActions ? (
              <div className="rv-record__actions">{mobileActions(row)}</div>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
