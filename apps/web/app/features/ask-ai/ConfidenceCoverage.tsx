"use client";

import { ChevronDown, CircleHelp, ShieldCheck } from "lucide-react";
import { useId, useState } from "react";

export type ConfidenceLabel = "high" | "medium" | "low" | "unknown";
export type ConfidenceMode =
  | "grounded_regulatory"
  | "general_ai"
  | "live_intelligence";
export type ConfidenceReasonKind =
  | "evidence"
  | "coverage"
  | "freshness"
  | "scope"
  | "capability";

export type ConfidenceReason = {
  kind: ConfidenceReasonKind;
  text: string;
};

export type ConfidenceSectionView = {
  sectionId: string;
  title: string;
  mode: ConfidenceMode;
  score: number;
  label: ConfidenceLabel;
  coveragePercent: number;
  critical: boolean;
  reasons: readonly ConfidenceReason[];
  gaps: readonly string[];
};

export type ConfidenceCoverageView = {
  score: number;
  label: ConfidenceLabel;
  coveragePercent: number;
  reasons: readonly ConfidenceReason[];
  gaps: readonly string[];
  officialDocumentCount: number;
  liveSourceCount: number;
  corpusFreshness: string;
  improvements: readonly string[];
  sections: readonly ConfidenceSectionView[];
};

const LABEL_RANK: Record<ConfidenceLabel, number> = {
  unknown: 0,
  low: 1,
  medium: 2,
  high: 3,
};

const MODE_COPY = {
  grounded_regulatory: "Official Regulatory Corpus",
  general_ai: "General AI Knowledge",
  live_intelligence: "Live Web Sources",
} as const;

const LABEL_COPY = {
  high: {
    title: "High confidence",
    description: "Strong admitted evidence and coverage.",
  },
  medium: {
    title: "Medium confidence",
    description: "Useful evidence with stated limits.",
  },
  low: {
    title: "Low confidence",
    description: "Material gaps or degraded evidence.",
  },
  unknown: {
    title: "Unknown confidence",
    description: "Confidence cannot be established from available evidence.",
  },
} as const;

const REASON_KINDS = new Set<ConfidenceReasonKind>([
  "evidence",
  "coverage",
  "freshness",
  "scope",
  "capability",
]);
const INTROSPECTION_PATTERN =
  /\b(?:chain[- ]of[- ]thought|internal reasoning|hidden reasoning|model reasoning|system prompt|i think|i believe)\b/i;

function requireText(value: string, label: string) {
  if (!value.trim()) {
    throw new Error(`${label} cannot be blank`);
  }
}

function requirePercent(value: number, label: string) {
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${label} must be finite and between 0 and 100`);
  }
}

function requireCount(value: number, label: string) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
}

function numericLabel(score: number): ConfidenceLabel {
  if (score >= 80) return "high";
  if (score >= 60) return "medium";
  if (score >= 35) return "low";
  return "unknown";
}

function requireUniqueText(values: readonly string[], label: string) {
  values.forEach((value) => requireText(value, label));
  if (new Set(values).size !== values.length) {
    throw new Error(`${label} must be unique`);
  }
}

function validateReasons(
  reasons: readonly ConfidenceReason[],
  label: string,
) {
  if (reasons.length === 0) {
    throw new Error(`${label} requires evidence-based reasons`);
  }
  if (reasons.some((reason) => !REASON_KINDS.has(reason.kind))) {
    throw new Error(`${label} reason kind is not presentation-safe`);
  }
  requireUniqueText(
    reasons.map((reason) => reason.text),
    `${label} reasons`,
  );
  if (reasons.some((reason) => INTROSPECTION_PATTERN.test(reason.text))) {
    throw new Error(`${label} cannot expose model introspection`);
  }
}

function validateSnapshot(
  snapshot: {
    score: number;
    label: ConfidenceLabel;
    coveragePercent: number;
    reasons: readonly ConfidenceReason[];
    gaps: readonly string[];
  },
  label: string,
) {
  requirePercent(snapshot.score, `${label} score`);
  requirePercent(snapshot.coveragePercent, `${label} coverage`);
  validateReasons(snapshot.reasons, label);
  requireUniqueText(snapshot.gaps, `${label} gaps`);
  if (LABEL_RANK[snapshot.label] > LABEL_RANK[numericLabel(snapshot.score)]) {
    throw new Error(`${label} cannot exceed its numeric confidence band`);
  }
}

function validateView(view: ConfidenceCoverageView) {
  validateSnapshot(view, "Overall confidence");
  requireCount(view.officialDocumentCount, "Official document count");
  requireCount(view.liveSourceCount, "Live source count");
  requireText(view.corpusFreshness, "Corpus freshness");
  requireUniqueText(view.improvements, "Confidence improvements");
  if (view.sections.length === 0) {
    throw new Error("Confidence coverage requires sections");
  }
  const sectionIds = view.sections.map((section) => section.sectionId);
  requireUniqueText(sectionIds, "Confidence section IDs");

  for (const section of view.sections) {
    requireText(section.title, "Confidence section title");
    validateSnapshot(section, `Section ${section.sectionId}`);
    if (
      section.mode === "general_ai" &&
      section.label === "high"
    ) {
      throw new Error("General AI confidence cannot be High");
    }
  }

  const hasOfficial = view.sections.some(
    (section) => section.mode === "grounded_regulatory",
  );
  const hasLive = view.sections.some(
    (section) => section.mode === "live_intelligence",
  );
  if (hasOfficial !== (view.officialDocumentCount > 0)) {
    throw new Error("Official document count must match displayed modes");
  }
  if (hasLive !== (view.liveSourceCount > 0)) {
    throw new Error("Live source count must match displayed modes");
  }

  const critical = view.sections.filter((section) => section.critical);
  if (critical.length === 0) {
    throw new Error("Confidence coverage requires a critical section");
  }
  const weakestCritical = Math.min(
    ...critical.map((section) => LABEL_RANK[section.label]),
  );
  if (LABEL_RANK[view.label] > weakestCritical) {
    throw new Error("Overall confidence cannot exceed a critical section");
  }
}

function Meter({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="ask-confidence-meter">
      <div
        className="ask-confidence-meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value.toFixed(1)} out of 100`}
      >
        <span style={{ width: `${value}%` }} />
      </div>
      <span aria-hidden="true">{value.toFixed(1)}</span>
    </div>
  );
}

function ReasonList({
  reasons,
}: {
  reasons: readonly ConfidenceReason[];
}) {
  return (
    <ul className="ask-confidence-reasons">
      {reasons.map((reason) => (
        <li key={`${reason.kind}:${reason.text}`}>
          <span>{reason.kind}</span>
          {reason.text}
        </li>
      ))}
    </ul>
  );
}

function SectionConfidence({
  section,
}: {
  section: ConfidenceSectionView;
}) {
  const generatedId = useId().replaceAll(":", "");
  const titleId = `ask-section-confidence-${generatedId}`;
  const copy = LABEL_COPY[section.label];

  return (
    <article
      className={`ask-section-confidence ${section.label}`}
      data-mode={section.mode}
      data-critical={section.critical ? "true" : "false"}
      aria-labelledby={titleId}
    >
      <div className="ask-section-confidence-heading">
        <div>
          <p>{MODE_COPY[section.mode]}</p>
          <h4 id={titleId}>{section.title}</h4>
        </div>
        <span className="ask-confidence-label">{copy.title}</span>
      </div>
      <p>{copy.description}</p>
      {section.critical ? (
        <p className="ask-critical-section">Critical section</p>
      ) : null}
      <Meter label={`${section.title} confidence score`} value={section.score} />
      <Meter
        label={`${section.title} evidence coverage`}
        value={section.coveragePercent}
      />
      <ReasonList reasons={section.reasons} />
      {section.gaps.length ? (
        <div className="ask-confidence-gaps">
          <h5>Evidence gaps</h5>
          <ul>
            {section.gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

function coverageIndicator(view: ConfidenceCoverageView) {
  const modes = new Set(view.sections.map((section) => section.mode));
  if (modes.size > 1) {
    return "Mixed — Multiple provenance modes";
  }
  const mode = view.sections[0].mode;
  if (view.label === "low" || view.label === "unknown") {
    return "Limited — Incomplete or degraded evidence";
  }
  if (mode === "grounded_regulatory" && view.label === "high") {
    return "High — Officially grounded";
  }
  if (mode === "general_ai") {
    return "Medium — General AI knowledge";
  }
  if (mode === "live_intelligence") {
    return "Live — Source-backed, time-sensitive";
  }
  return `${LABEL_COPY[view.label].title} — Official evidence with stated limits`;
}

export function ConfidenceCoverage({
  view,
}: {
  view: ConfidenceCoverageView;
}) {
  validateView(view);
  const [expanded, setExpanded] = useState(false);
  const generatedId = useId().replaceAll(":", "");
  const panelId = `ask-confidence-panel-${generatedId}`;
  const copy = LABEL_COPY[view.label];

  return (
    <section className="ask-confidence-card" aria-labelledby={`${panelId}-title`}>
      <div className="ask-confidence-summary">
        <span className="ask-confidence-shield" aria-hidden="true">
          <ShieldCheck size={21} />
        </span>
        <div>
          <h3 id={`${panelId}-title`}>Confidence and coverage</h3>
          <p>
            <strong>{copy.title}</strong> · {copy.description}
          </p>
        </div>
        <button
          type="button"
          className="ask-confidence-toggle"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Hide explanation" : "Why this confidence?"}
          <ChevronDown
            size={17}
            aria-hidden="true"
            className={expanded ? "expanded" : undefined}
          />
        </button>
      </div>

      <div className="ask-confidence-overview">
        <p className="ask-confidence-indicator">{coverageIndicator(view)}</p>
        <Meter label="Overall confidence score" value={view.score} />
        <Meter label="Overall evidence coverage" value={view.coveragePercent} />
        <p className="ask-confidence-not-probability">
          <CircleHelp size={16} aria-hidden="true" />
          This evidence confidence score is not a probability of legal
          correctness.
        </p>
      </div>

      <div id={panelId} hidden={!expanded}>
        <div className="ask-confidence-evidence-summary">
          <div>
            <strong>{view.officialDocumentCount}</strong>
            <span>Official documents found</span>
          </div>
          <div>
            <strong>{view.liveSourceCount}</strong>
            <span>Live sources found</span>
          </div>
          <div>
            <strong>Corpus freshness</strong>
            <span>{view.corpusFreshness}</span>
          </div>
        </div>

        <div className="ask-confidence-detail-block">
          <h4>Why this confidence is shown</h4>
          <ReasonList reasons={view.reasons} />
        </div>

        {view.gaps.length ? (
          <div className="ask-confidence-detail-block">
            <h4>What evidence is missing</h4>
            <ul>
              {view.gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {view.improvements.length ? (
          <div className="ask-confidence-detail-block">
            <h4>What would improve confidence</h4>
            <ul>
              {view.improvements.map((improvement) => (
                <li key={improvement}>{improvement}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="ask-section-confidence-grid">
          {view.sections.map((section) => (
            <SectionConfidence key={section.sectionId} section={section} />
          ))}
        </div>
      </div>
    </section>
  );
}
