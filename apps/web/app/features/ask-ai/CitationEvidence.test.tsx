import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildCitationSelection } from "../../../lib/ask-ai-citations";
import {
  CitationEvidencePanel,
  InlineCitation,
} from "./CitationEvidence";

afterEach(() => {
  cleanup();
});

const MESSAGE_ID = "33333333-3333-4333-8333-333333333333";
const CLAIM_ID = "99999999-9999-4999-8999-999999999999";
const CITATION_ID = "88888888-8888-4888-8888-888888888888";
const SOURCE_ID = "66666666-6666-4666-8666-666666666666";

function source(overrides: Record<string, unknown> = {}) {
  return {
    id: SOURCE_ID,
    ordinal: 0,
    source_key: "official:consultation",
    source_class: "official",
    source_type: "regulation",
    document_id: 91,
    document_version_id: 92,
    chunk_id: 93,
    graph_reference: null,
    title_snapshot: "Consultation regulation",
    url_snapshot: "https://official.example.test/consultation",
    issuer_snapshot: "Regulator",
    publisher_snapshot: null,
    jurisdiction_snapshot: "central",
    published_at: "2026-07-27T08:30:00Z",
    retrieved_at: "2026-07-27T09:04:00Z",
    evidence_snapshot: "Responses are due by 31 August.",
    locator_snapshot: "paragraph 4",
    content_hash: "sha256:contract",
    metadata: { language: "en" },
    created_at: "2026-07-27T09:04:00Z",
    ...overrides,
  };
}

function claim(overrides: Record<string, unknown> = {}) {
  return {
    id: CLAIM_ID,
    section_id: "77777777-7777-4777-8777-777777777777",
    ordinal: 0,
    knowledge_mode: "grounded_regulatory",
    claim_text: "The consultation deadline is 31 August.",
    is_material: true,
    support_status: "supported",
    support_score: 0.98,
    model: "composer-1",
    policy_version: "composer-policy-1",
    prompt_version: "composer-prompt-1",
    required_disclosure: null,
    verifier_model: "model-1",
    verifier_policy_version: "ask-ai-claim-verifier-v1",
    created_at: "2026-07-27T09:04:00Z",
    ...overrides,
  };
}

function citation(overrides: Record<string, unknown> = {}) {
  return {
    id: CITATION_ID,
    claim_id: CLAIM_ID,
    source_id: SOURCE_ID,
    ordinal: 0,
    claim_knowledge_mode: "grounded_regulatory",
    source_class: "official",
    citation_kind: "claim_support",
    marker: "[1]",
    evidence_snapshot: "Responses are due by 31 August.",
    locator_snapshot: "paragraph 4",
    support_score: 0.98,
    verification_status: "supported",
    verifier_model: "model-1",
    verifier_policy_version: "ask-ai-claim-verifier-v1",
    created_at: "2026-07-27T09:04:00Z",
    ...overrides,
  };
}

function selection(overrides: {
  citation?: Record<string, unknown>;
  claim?: Record<string, unknown>;
  source?: Record<string, unknown>;
} = {}) {
  return buildCitationSelection({
    messageId: MESSAGE_ID,
    responseVersion: 2,
    citation: citation(overrides.citation),
    claim: claim(overrides.claim),
    source: source(overrides.source),
  });
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1",
    message_id: MESSAGE_ID,
    response_version: 2,
    claim_id: CLAIM_ID,
    claim_key: "claim-1",
    claim_ordinal: 0,
    claim_text: "The consultation deadline is 31 August.",
    support_status: "supported",
    support_score: 0.98,
    citation_id: CITATION_ID,
    evidence_key: "evidence-1",
    citation_ordinal: 0,
    marker: "[1]",
    verification_status: "supported",
    verifier_provider: "contract-verifier",
    verifier_version: "verifier-1",
    verifier_model: "model-1",
    verifier_prompt_version: "prompt-1",
    verifier_policy_version: "ask-ai-claim-verifier-v1",
    verification_latency_ms: 125,
    verification: {
      outcome: "supported",
      confidence: 0.98,
      publication_mode: "evidence_only",
      final_claim_text: "The consultation deadline is 31 August.",
      terminal_reason: "CLAIM_VERIFIER_RELEASE_NOT_APPROVED",
      latency_ms: 125,
      evidence_ids: ["evidence-1"],
      correction_applied: false,
      verifier_identity: {
        provider: "contract-verifier",
        verifier_version: "verifier-1",
        model_version: "model-1",
        prompt_version: "prompt-1",
        policy_version: "ask-ai-claim-verifier-v1",
      },
    },
    provenance: { knowledge_mode: "grounded_regulatory" },
    confidence_result: { score: 0.98 },
    source: source(),
    current_source_status: "current",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("Ask AI E7.7 citation evidence UI", () => {
  it("builds only an exact official claim/source selection", () => {
    expect(selection()).toMatchObject({
      citation_id: CITATION_ID,
      claim_id: CLAIM_ID,
      source_id: SOURCE_ID,
      source_title: "Consultation regulation",
      marker: "[1]",
    });

    expect(() =>
      selection({ citation: { source_id: CLAIM_ID } }),
    ).toThrow(/source identity/i);
    expect(() =>
      selection({ claim: { knowledge_mode: "general_ai" } }),
    ).toThrow(/grounded/i);
  });

  it("makes a verified inline citation keyboard-operable", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    const selected = selection();

    render(<InlineCitation selection={selected} onInspect={inspect} />);

    const button = screen.getByRole("button", {
      name: /inspect citation \[1\].*supported/i,
    });
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(inspect).toHaveBeenCalledWith(selected);
  });

  it("keeps unverified citations non-interactive and names their state", () => {
    render(
      <InlineCitation
        selection={selection({
          citation: { verification_status: "pending" },
        })}
        onInspect={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("[1] Verifying citation…")).toHaveAttribute(
      "data-verification-state",
      "pending",
    );
  });

  it("shows saved identity immediately and progressively loads current detail", async () => {
    const pending = deferred<unknown>();
    const selected = selection();
    render(
      <CitationEvidencePanel
        selection={selected}
        loadDetail={() => pending.promise}
        onClose={vi.fn()}
      />,
    );

    const panel = screen.getByRole("complementary", {
      name: "Citation evidence",
    });
    expect(within(panel).getByText("Consultation regulation")).toBeInTheDocument();
    expect(
      within(panel).getByText("Responses are due by 31 August."),
    ).toBeInTheDocument();
    expect(within(panel).getByText("Checking current source status…")).toBeInTheDocument();

    pending.resolve(detail());
    expect(await within(panel).findByText("Current source")).toBeInTheDocument();
    expect(within(panel).getByText("Regulator")).toBeInTheDocument();
    expect(
      within(panel).getByRole("link", { name: "Open official source" }),
    ).toHaveAttribute(
      "href",
      "https://official.example.test/consultation",
    );
  });

  it("retains the stored snapshot when current detail fails safely", async () => {
    const load = vi.fn().mockRejectedValue(new Error("secret provider detail"));
    render(
      <CitationEvidencePanel
        selection={selection()}
        loadDetail={load}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByText(
        "Current source details could not be loaded. The saved citation snapshot remains available.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Responses are due by 31 August.")).toBeInTheDocument();
    expect(screen.queryByText("secret provider detail")).not.toBeInTheDocument();
  });

  it("shows superseded status without replacing the saved citation", async () => {
    render(
      <CitationEvidencePanel
        selection={selection()}
        loadDetail={vi.fn().mockResolvedValue(
          detail({ current_source_status: "superseded" }),
        )}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("Superseded source")).toBeInTheDocument();
    expect(screen.getByText("Responses are due by 31 August.")).toBeInTheDocument();
  });

  it("refuses unsafe source links while retaining source identity", async () => {
    render(
      <CitationEvidencePanel
        selection={selection({ source: { url_snapshot: "javascript:alert(1)" } })}
        loadDetail={vi.fn().mockResolvedValue(
          detail({ source: source({ url_snapshot: "javascript:alert(1)" }) }),
        )}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("Current source")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Source link unavailable")).toBeInTheDocument();
    expect(screen.getByText("Consultation regulation")).toBeInTheDocument();
  });

  it("supports close by button and Escape without trapping canvas focus", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(
      <CitationEvidencePanel
        selection={selection()}
        loadDetail={vi.fn().mockResolvedValue(detail())}
        onClose={close}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Close evidence panel" }));
    expect(close).toHaveBeenCalledTimes(1);
    await user.keyboard("{Escape}");
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("ignores stale detail after the selected citation changes", async () => {
    const first = deferred<unknown>();
    const load = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce(
        detail({
          citation_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          source: source({ title_snapshot: "Second source" }),
        }),
      );
    const { rerender } = render(
      <CitationEvidencePanel
        selection={selection()}
        loadDetail={load}
        onClose={vi.fn()}
      />,
    );
    const second = selection({
      citation: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
      source: { title_snapshot: "Second source" },
    });
    rerender(
      <CitationEvidencePanel
        selection={second}
        loadDetail={load}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("Second source")).toBeInTheDocument();
    first.resolve(detail());
    await waitFor(() => {
      expect(screen.getByText("Second source")).toBeInTheDocument();
    });
    expect(load).toHaveBeenCalledTimes(2);
  });
});
