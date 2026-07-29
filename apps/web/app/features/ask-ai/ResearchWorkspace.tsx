"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import {
  useFederatedResearchSearch,
  useResearchWorkspaceScope,
  useResolveResearchEntity,
} from "@/lib/ask-ai-data";
import type {
  AskEntityLookupCandidate,
  AskEntityLookupResponse,
} from "@/lib/ask-ai-entities";
import type {
  AskFederatedSearchRequest,
  AskFederatedSearchResponse,
  AskSearchItem,
} from "@/lib/ask-ai-search";

import { EntityLookupCanvas } from "./EntityLookupCanvas";
import { FederatedSearchResults } from "./FederatedSearchResults";
import {
  ResearchSessionRail,
  type ResearchExportDownloader,
} from "./ResearchSessionRail";
import {
  ResearchWorkspaceShell,
  type ResearchSubmitCapability,
} from "./ResearchWorkspaceShell";

export function ResearchWorkspace({
  onSubmit,
  downloadExport,
  entityCorePage = null,
}: {
  onSubmit?: ResearchSubmitCapability;
  downloadExport?: ResearchExportDownloader;
  entityCorePage?: unknown | null;
}) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [entityResult, setEntityResult] =
    useState<AskEntityLookupResponse | null>(null);
  const [entityError, setEntityError] = useState<string | null>(null);
  const [searchResult, setSearchResult] =
    useState<AskFederatedSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchFilters, setSearchFilters] = useState<
    AskFederatedSearchRequest["filters"]
  >({});
  const restoredRouteRef = useRef(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSequenceRef = useRef(0);
  const searchDraftRef = useRef("");
  const searchCorrectionModeRef = useRef<"auto" | "original">("auto");
  const workspaceScope = useResearchWorkspaceScope();
  const entityLookup = useResolveResearchEntity();
  const federatedSearch = useFederatedResearchSearch();
  const resolveEntity = entityLookup.mutateAsync;
  const searchResearch = federatedSearch.mutateAsync;

  const lookupEntity = useCallback(
    async (mention: string, updateRoute: boolean) => {
      searchSequenceRef.current += 1;
      setSearchResult(null);
      setSearchError(null);
      setEntityError(null);
      try {
        const result = await resolveEntity({ mention });
        setEntityResult(result);
        setActiveSessionId(null);
        if (
          updateRoute &&
          result.status === "resolved" &&
          result.selected !== null
        ) {
          window.history.pushState(
            { entity: result.selected.canonical_id },
            "",
            result.selected.entity_route,
          );
        }
      } catch {
        setEntityError(
          "Try again. No database, provider, or diagnostic details were exposed.",
        );
        throw new Error("Entity lookup failed");
      }
    },
    [resolveEntity],
  );

  const runSearch = useCallback(
    async (
      query: string,
      filters: AskFederatedSearchRequest["filters"],
      correctionMode: "auto" | "original" = "auto",
    ) => {
      const sequence = searchSequenceRef.current + 1;
      searchSequenceRef.current = sequence;
      setSearchError(null);
      try {
        const result = await searchResearch({
          schema_version: "1",
          query,
          correction_mode: correctionMode,
          filters,
          limit: 5,
        });
        if (searchSequenceRef.current === sequence) {
          setSearchResult(result);
        }
      } catch {
        if (searchSequenceRef.current === sequence) {
          setSearchError(
            "Try again. No database, provider, or diagnostic details were exposed.",
          );
        }
      }
    },
    [searchResearch],
  );

  useEffect(
    () => () => {
      if (searchTimerRef.current !== null) {
        clearTimeout(searchTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (!workspaceScope.enabled) return;
    const restoreRoute = () => {
      const route = new URLSearchParams(window.location.search);
      const canonicalId = route.get("entity");
      const sessionId = route.get("session");
      if (
        entityLookup.available &&
        canonicalId !== null &&
        canonicalId.trim().length > 0
      ) {
        void lookupEntity(canonicalId, false).catch(() => undefined);
      } else if (sessionId !== null && sessionId.trim().length > 0) {
        setActiveSessionId(sessionId);
        setEntityResult(null);
        setEntityError(null);
      }
    };
    if (!restoredRouteRef.current) {
      restoredRouteRef.current = true;
      restoreRoute();
    }
    window.addEventListener("popstate", restoreRoute);
    return () => window.removeEventListener("popstate", restoreRoute);
  }, [entityLookup.available, lookupEntity, workspaceScope.enabled]);

  const internalEntitySubmit =
    workspaceScope.enabled && entityLookup.available
      ? async ({ question }: { question: string }) => {
          await lookupEntity(question, true);
        }
      : undefined;
  const submitCapability = onSubmit ?? internalEntitySubmit;

  async function chooseEntity(candidate: AskEntityLookupCandidate) {
    await lookupEntity(candidate.canonical_id, true);
  }

  function resetResearch() {
    searchSequenceRef.current += 1;
    if (searchTimerRef.current !== null) {
      clearTimeout(searchTimerRef.current);
      searchTimerRef.current = null;
    }
    setActiveSessionId(null);
    setEntityResult(null);
    setEntityError(null);
    setSearchResult(null);
    setSearchError(null);
    setSearchFilters({});
    searchDraftRef.current = "";
    searchCorrectionModeRef.current = "auto";
    const url = new URL(window.location.href);
    url.searchParams.delete("entity");
    window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function updateSearchDraft(draft: string) {
    if (searchTimerRef.current !== null) {
      clearTimeout(searchTimerRef.current);
    }
    const query = draft.trim();
    searchDraftRef.current = query;
    searchCorrectionModeRef.current = "auto";
    if (
      query.length < 2 ||
      !workspaceScope.enabled ||
      !federatedSearch.available
    ) {
      searchSequenceRef.current += 1;
      setSearchResult(null);
      setSearchError(null);
      return;
    }
    searchTimerRef.current = setTimeout(() => {
      void runSearch(query, searchFilters);
    }, 250);
  }

  function selectSearchResult(item: AskSearchItem) {
    if (item.result_type === "entity") {
      const canonicalId = item.result_id.slice("entity:".length);
      void lookupEntity(canonicalId, true).catch(() => undefined);
      return;
    }
    if (item.result_type === "previous_research") {
      const sessionId = item.result_id.slice(
        "previous_research:".length,
      );
      setActiveSessionId(sessionId);
      setEntityResult(null);
      setEntityError(null);
      window.history.pushState(
        { session: sessionId },
        "",
        item.route,
      );
      return;
    }
    window.location.assign(item.route);
  }

  function moveFromComposer(
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (event.key !== "ArrowDown") return false;
    const first = document.querySelector<HTMLElement>(
      "[data-search-option]",
    );
    if (first === null) return false;
    event.preventDefault();
    first.focus();
    return true;
  }

  return (
    <ResearchWorkspaceShell
      onSubmit={submitCapability}
      onNewResearch={resetResearch}
      onDraftChange={updateSearchDraft}
      onComposerKeyDown={moveFromComposer}
      navigationContent={
        <ResearchSessionRail
          activeSessionId={activeSessionId}
          onSelectSession={(session) => {
            setActiveSessionId(session.id);
            setEntityResult(null);
            setEntityError(null);
          }}
          onSessionUnavailable={(sessionId) => {
            setActiveSessionId((current) =>
              current === sessionId ? null : current,
            );
          }}
          downloadExport={downloadExport}
        />
      }
      canvasContent={
        onSubmit === undefined ? (
          entityResult === null &&
          (searchResult !== null ||
            searchError !== null ||
            federatedSearch.isPending) ? (
            <FederatedSearchResults
              result={searchResult}
              pending={federatedSearch.isPending}
              error={searchError}
              onSelect={selectSearchResult}
              onRestoreOriginal={(query) => {
                searchCorrectionModeRef.current = "original";
                void runSearch(query, searchFilters, "original");
              }}
              filters={searchFilters}
              onFiltersChange={(filters) => {
                setSearchFilters(filters);
                if (searchDraftRef.current.length >= 2) {
                  void runSearch(
                    searchDraftRef.current,
                    filters,
                    searchCorrectionModeRef.current,
                  );
                }
              }}
            />
          ) : (
            <EntityLookupCanvas
              result={entityResult}
              corePage={entityCorePage}
              error={entityError}
              selecting={entityLookup.isPending}
              onChoose={(candidate) => {
                void chooseEntity(candidate).catch(() => undefined);
              }}
            />
          )
        ) : undefined
      }
    />
  );
}
