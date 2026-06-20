"use client";

import {
  AlertTriangle,
  Bell,
  Bookmark,
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  Filter,
  MessageSquareText,
  Play,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

type EventType = "NEW" | "CHANGED" | "REPLACEMENT" | "DUPLICATE";

type RegulatoryEvent = {
  id: number;
  title: string;
  source: string;
  jurisdiction: "central" | "state";
  eventType: EventType;
  issueDate: string;
  detectedAt: string;
  topics: string[];
  summary: string;
  whyItMatters: string;
  sourceUrl: string;
  confidence: "high" | "medium" | "low";
  affected: string[];
};

const events: RegulatoryEvent[] = [
  {
    id: 101,
    title: "MNRE monthly policy and regulatory update",
    source: "Ministry of New & Renewable Energy",
    jurisdiction: "central",
    eventType: "NEW",
    issueDate: "2026-06-18",
    detectedAt: "2026-06-20 07:00 IST",
    topics: ["solar", "RPO/REC", "tariff"],
    summary:
      "Layer-1 digest parser detected a central renewable-energy item and queued the primary document for grounded extraction.",
    whyItMatters:
      "Digest-origin records let the pipeline avoid missing updates hidden inside monthly PDFs while keeping primary documents as the final source of truth.",
    sourceUrl: "https://mnre.gov.in/en/monthly-updates/",
    confidence: "medium",
    affected: ["renewable procurement", "solar developers", "DISCOM teams"],
  },
  {
    id: 102,
    title: "CERC order watch: tariff and open access flagged",
    source: "Central Electricity Regulatory Commission",
    jurisdiction: "central",
    eventType: "CHANGED",
    issueDate: "2026-06-17",
    detectedAt: "2026-06-20 07:01 IST",
    topics: ["tariff", "open access", "transmission"],
    summary:
      "A conditional re-check path is ready to compare file and content hashes once the crawler is connected to storage.",
    whyItMatters:
      "Same-URL regulatory replacements are a real risk. The version baseline is designed to surface them instead of silently overwriting history.",
    sourceUrl: "https://cercind.gov.in/",
    confidence: "medium",
    affected: ["open-access consumers", "transmission planners"],
  },
  {
    id: 103,
    title: "Ministry of Power notification queue item",
    source: "Ministry of Power",
    jurisdiction: "central",
    eventType: "NEW",
    issueDate: "Pending audit",
    detectedAt: "2026-06-20 07:02 IST",
    topics: ["storage", "transmission"],
    summary:
      "The Tier-0 source is configured and visible in admin source health while live discovery waits for the audit pass.",
    whyItMatters:
      "Separating source audit from crawling keeps government-site monitoring polite and reduces blocked-run surprises.",
    sourceUrl: "https://powermin.gov.in/en",
    confidence: "low",
    affected: ["grid planning", "storage developers"],
  },
];

const sourceHealth = [
  { code: "mnre", name: "MNRE", mode: "digest", state: "ready", failures: 0 },
  { code: "cerc", name: "CERC", mode: "agent", state: "audit", failures: 0 },
  { code: "mop", name: "MoP", mode: "agent", state: "audit", failures: 0 },
];

const topicOptions = ["all", "solar", "tariff", "open access", "RPO/REC", "storage"];

const navItems: Array<{ label: string; Icon: LucideIcon }> = [
  { label: "Digest", Icon: FileText },
  { label: "Sources", Icon: Database },
  { label: "Chat", Icon: MessageSquareText },
  { label: "Notifications", Icon: Bell },
  { label: "Settings", Icon: Settings },
];

function eventTone(type: EventType) {
  if (type === "CHANGED") return "border-amber-300 bg-amber-50 text-amber-800";
  if (type === "REPLACEMENT") return "border-violet-300 bg-violet-50 text-violet-800";
  if (type === "DUPLICATE") return "border-zinc-300 bg-zinc-50 text-zinc-700";
  return "border-teal-300 bg-teal-50 text-teal-800";
}

export default function Home() {
  const [selectedId, setSelectedId] = useState(events[0].id);
  const [topic, setTopic] = useState("all");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("What changed and who is affected?");
  const selected = events.find((event) => event.id === selectedId) ?? events[0];

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      const matchesTopic = topic === "all" || event.topics.includes(topic);
      const haystack = `${event.title} ${event.source} ${event.topics.join(" ")}`.toLowerCase();
      return matchesTopic && haystack.includes(query.toLowerCase());
    });
  }, [query, topic]);

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[248px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--line)] bg-[#18201d] px-5 py-5 text-white lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#16a394]">
              <ShieldCheck size={22} aria-hidden />
            </div>
            <div>
              <p className="text-base font-semibold">Regulatory AI</p>
              <p className="text-xs text-white/65">Energy intelligence</p>
            </div>
          </div>

          <nav className="mt-8 grid gap-1 text-sm">
            {navItems.map(({ label, Icon }) => (
              <button
                key={label}
                className="flex h-10 items-center gap-3 rounded-md px-3 text-left text-white/78 hover:bg-white/10"
                title={label}
              >
                <Icon size={17} aria-hidden />
                <span>{label}</span>
              </button>
            ))}
          </nav>

          <div className="mt-8 border-t border-white/15 pt-5">
            <p className="text-xs text-white/55">Next run</p>
            <div className="mt-2 flex items-center justify-between text-sm">
              <span>07:00 IST</span>
              <button
                className="grid h-8 w-8 place-items-center rounded-md bg-white/10 hover:bg-white/15"
                title="Run now"
              >
                <Play size={16} aria-hidden />
              </button>
            </div>
          </div>
        </aside>

        <section className="min-w-0">
          <header className="border-b border-[var(--line)] bg-white px-4 py-4 sm:px-6">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h1 className="text-2xl font-semibold">Daily regulatory digest</h1>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  3 Tier-0 sources configured. Live providers are pending keys.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm sm:flex">
                <Metric label="Events" value="3" tone="teal" />
                <Metric label="Sources" value="3/3" tone="violet" />
                <Metric label="Failures" value="0" tone="amber" />
              </div>
            </div>
          </header>

          <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[minmax(360px,0.86fr)_minmax(420px,1.14fr)]">
            <div className="grid gap-4">
              <section className="border border-[var(--line)] bg-white p-3">
                <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
                  <label className="flex h-11 items-center gap-2 border border-[var(--line)] bg-white px-3">
                    <Search size={17} aria-hidden />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                      placeholder="Search title, source, topic"
                    />
                  </label>
                  <label className="flex h-11 items-center gap-2 border border-[var(--line)] bg-white px-3">
                    <Filter size={17} aria-hidden />
                    <select
                      value={topic}
                      onChange={(event) => setTopic(event.target.value)}
                      className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                    >
                      {topicOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </section>

              <section className="grid gap-2">
                {filteredEvents.map((event) => (
                  <button
                    key={event.id}
                    onClick={() => setSelectedId(event.id)}
                    className={`border bg-white p-4 text-left transition hover:border-[#8fb7ad] ${
                      selectedId === event.id ? "border-[#0f766e]" : "border-[var(--line)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold leading-5">{event.title}</p>
                        <p className="mt-1 truncate text-xs text-[var(--muted)]">{event.source}</p>
                      </div>
                      <span
                        className={`shrink-0 border px-2 py-1 text-xs font-medium ${eventTone(
                          event.eventType,
                        )}`}
                      >
                        {event.eventType}
                      </span>
                    </div>
                    <p className="mt-3 line-clamp-2 text-sm leading-6 text-[#485650]">{event.summary}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {event.topics.map((item) => (
                        <span key={item} className="border border-[var(--line)] px-2 py-1 text-xs">
                          {item}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </section>

              <section className="border border-[var(--line)] bg-white p-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Source health</h2>
                  <Wifi size={17} className="text-[#0f766e]" aria-hidden />
                </div>
                <div className="mt-3 grid gap-2">
                  {sourceHealth.map((source) => (
                    <div
                      key={source.code}
                      className="grid grid-cols-[56px_1fr_70px_36px] items-center gap-2 border border-[var(--line)] px-3 py-2 text-sm"
                    >
                      <span className="font-medium">{source.name}</span>
                      <span className="text-xs text-[var(--muted)]">{source.mode}</span>
                      <span className="text-xs text-[var(--muted)]">{source.state}</span>
                      {source.failures === 0 ? (
                        <CheckCircle2 size={16} className="text-[#0f766e]" aria-hidden />
                      ) : (
                        <AlertTriangle size={16} className="text-[#b42318]" aria-hidden />
                      )}
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-4">
              <section className="border border-[var(--line)] bg-white">
                <div className="border-b border-[var(--line)] p-5">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`border px-2 py-1 text-xs font-medium ${eventTone(selected.eventType)}`}>
                          {selected.eventType}
                        </span>
                        <span className="border border-[var(--line)] px-2 py-1 text-xs">
                          {selected.confidence} confidence
                        </span>
                      </div>
                      <h2 className="mt-3 max-w-3xl text-xl font-semibold leading-7">{selected.title}</h2>
                      <p className="mt-2 text-sm text-[var(--muted)]">
                        {selected.source} - {selected.detectedAt}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button className="grid h-9 w-9 place-items-center border border-[var(--line)]" title="Bookmark">
                        <Bookmark size={17} aria-hidden />
                      </button>
                      <a
                        href={selected.sourceUrl}
                        className="grid h-9 w-9 place-items-center border border-[var(--line)]"
                        title="Open source"
                      >
                        <ExternalLink size={17} aria-hidden />
                      </a>
                    </div>
                  </div>
                </div>

                <div className="grid gap-5 p-5 lg:grid-cols-[1fr_240px]">
                  <div>
                    <h3 className="text-sm font-semibold">Grounded summary</h3>
                    <p className="mt-2 text-sm leading-6 text-[#3f4c47]">{selected.summary}</p>
                    <h3 className="mt-5 text-sm font-semibold">Why it matters</h3>
                    <p className="mt-2 text-sm leading-6 text-[#3f4c47]">{selected.whyItMatters}</p>
                    <div className="mt-5 flex flex-wrap gap-2">
                      {selected.affected.map((item) => (
                        <span key={item} className="border border-[var(--line)] px-2 py-1 text-xs">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <DocumentPreview />
                </div>
              </section>

              <section className="border border-[var(--line)] bg-white">
                <div className="border-b border-[var(--line)] p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquareText size={18} className="text-[#0f766e]" aria-hidden />
                      <h2 className="text-sm font-semibold">Insight chat</h2>
                    </div>
                    <span className="text-xs text-[var(--muted)]">offline mode</span>
                  </div>
                </div>
                <div className="grid gap-3 p-4">
                  <div className="border border-[#c9d8d3] bg-[#f1fbf8] p-3 text-sm leading-6 text-[#244842]">
                    I can show the workflow, but live insight chat needs an LLM API key. Once configured,
                    answers will use only the selected update and extracted document text.
                  </div>
                  <label className="grid gap-2">
                    <span className="text-xs font-medium text-[var(--muted)]">Ask about this update</span>
                    <div className="grid grid-cols-[1fr_40px] gap-2">
                      <input
                        value={message}
                        onChange={(event) => setMessage(event.target.value)}
                        className="h-10 min-w-0 border border-[var(--line)] px-3 text-sm outline-none focus:border-[#0f766e]"
                      />
                      <button
                        className="grid h-10 w-10 place-items-center border border-[#0f766e] bg-[#0f766e] text-white"
                        title="Send"
                      >
                        <Send size={17} aria-hidden />
                      </button>
                    </div>
                  </label>
                </div>
              </section>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "teal" | "violet" | "amber" }) {
  const color =
    tone === "teal" ? "text-[#0f766e]" : tone === "violet" ? "text-[#6941c6]" : "text-[#b7791f]";
  return (
    <div className="border border-[var(--line)] bg-white px-3 py-2">
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <p className={`text-lg font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function DocumentPreview() {
  return (
    <div className="border border-[var(--line)] bg-[#fbfcfa] p-3">
      <div className="flex items-center justify-between text-xs text-[var(--muted)]">
        <span>Primary document</span>
        <FileText size={15} aria-hidden />
      </div>
      <div className="mt-3 grid gap-2">
        <div className="h-3 w-10/12 bg-[#cbd5d0]" />
        <div className="h-3 w-8/12 bg-[#d9dfdc]" />
        <div className="mt-2 h-20 border border-[#d5ddd8] bg-white p-2">
          <div className="grid grid-cols-3 gap-1">
            {Array.from({ length: 12 }).map((_, index) => (
              <div
                key={index}
                className={`h-2 ${index % 4 === 0 ? "bg-[#0f766e]" : "bg-[#dde5e1]"}`}
              />
            ))}
          </div>
        </div>
        <div className="grid grid-cols-4 gap-1">
          <div className="h-2 bg-[#6941c6]" />
          <div className="h-2 bg-[#dbe0dc]" />
          <div className="h-2 bg-[#b7791f]" />
          <div className="h-2 bg-[#dbe0dc]" />
        </div>
      </div>
    </div>
  );
}
