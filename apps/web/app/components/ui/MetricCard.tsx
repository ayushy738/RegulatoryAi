import type { LucideIcon } from "lucide-react";

import { compactNumber } from "@/app/workspace/format";

export function MetricCard({
  title,
  value,
  Icon,
  tone,
}: {
  title: string;
  value: number | string;
  Icon: LucideIcon;
  tone: "purple" | "green" | "amber" | "red";
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div>
        <span>{title}</span>
        <strong>{typeof value === "number" ? compactNumber(value) : value}</strong>
      </div>
      <Icon size={22} />
    </article>
  );
}
