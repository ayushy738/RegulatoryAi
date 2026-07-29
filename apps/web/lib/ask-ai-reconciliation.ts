"use client";

import {
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  InfiniteData,
  QueryClient,
} from "@tanstack/react-query";
import { useMemo } from "react";
import { z } from "zod";

import {
  researchWorkspaceKeys,
  useResearchTurns,
  useResearchWorkspaceScope,
} from "./ask-ai-data";
import {
  askTurnSchema,
} from "./ask-ai-turns";
import type {
  AskTurn,
  AskTurnList,
} from "./ask-ai-turns";

const safeErrorCode = /^[A-Z][A-Z0-9_]{0,99}$/;

function validateOptimisticTurn(
  turn: AskTurn,
  context: z.RefinementCtx,
) {
  if (
    turn.user_message === null ||
    turn.user_message.role !== "user" ||
    turn.id !== turn.user_message.id
  ) {
    context.addIssue({
      code: "custom",
      message: "Optimistic turns require their user message as anchor",
    });
  }
  if (
    turn.assistant_message !== null &&
    turn.assistant_message.role !== "assistant"
  ) {
    context.addIssue({
      code: "custom",
      message: "Optimistic assistant placeholders require assistant role",
    });
  }
  if (turn.run !== null) {
    context.addIssue({
      code: "custom",
      message: "Optimistic turns cannot claim a persisted run",
    });
  }
  if (
    turn.user_message !== null &&
    turn.assistant_message !== null &&
    turn.user_message.event_id !== turn.assistant_message.event_id
  ) {
    context.addIssue({
      code: "custom",
      message: "Optimistic messages require one event scope",
    });
  }
}

export const researchPendingTurnInputSchema = z
  .strictObject({
    session_id: z.uuid(),
    idempotency_key: z.uuid(),
    turn: askTurnSchema,
  })
  .superRefine((value, context) =>
    validateOptimisticTurn(value.turn, context),
  );

export const researchTurnReconciliationSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    session_id: z.uuid(),
    idempotency_key: z.uuid(),
    state: z.enum(["saving", "unsynced", "synced"]),
    turn: askTurnSchema,
    safe_error_code: z.string().regex(safeErrorCode).nullable(),
    persisted_turn_id: z.uuid().nullable(),
    resolved_turn: askTurnSchema.nullable(),
  })
  .superRefine((value, context) => {
    validateOptimisticTurn(value.turn, context);
    if (
      value.state === "saving" &&
      (value.safe_error_code !== null ||
        value.persisted_turn_id !== null ||
        value.resolved_turn !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Saving turns cannot claim failure or persistence",
      });
    }
    if (
      value.state === "unsynced" &&
      (value.safe_error_code === null ||
        value.persisted_turn_id !== null ||
        value.resolved_turn !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Unsynced turns require only a safe failure code",
      });
    }
    if (
      value.state === "synced" &&
      (value.safe_error_code !== null ||
        value.persisted_turn_id !== value.turn.id ||
        (value.resolved_turn !== null &&
          value.resolved_turn.id !== value.turn.id))
    ) {
      context.addIssue({
        code: "custom",
        message: "Synced turns require their exact persisted anchor",
      });
    }
    if (
      value.resolved_turn !== null &&
      (value.turn.user_message === null ||
        value.resolved_turn.user_message === null ||
        value.resolved_turn.user_message.id !==
          value.turn.user_message.id ||
        value.resolved_turn.user_message.content !==
          value.turn.user_message.content ||
        value.resolved_turn.user_message.event_id !==
          value.turn.user_message.event_id ||
        (value.turn.assistant_message !== null &&
          value.resolved_turn.assistant_message?.id !==
            value.turn.assistant_message.id))
    ) {
      context.addIssue({
        code: "custom",
        message: "Resolved turns must retain optimistic stable identity",
      });
    }
  });

export type ResearchPendingTurnInput = z.infer<
  typeof researchPendingTurnInputSchema
>;
export type ResearchTurnReconciliation = z.infer<
  typeof researchTurnReconciliationSchema
>;

const researchPendingTurnCreationSchema = z.strictObject({
  session_id: z.uuid(),
  content: z.string().trim().min(1),
  event_id: z.number().int().nullable().optional(),
  idempotency_key: z.uuid().optional(),
  user_message_id: z.uuid().optional(),
  created_at: z.iso.datetime({ offset: true }).optional(),
});

export function createResearchPendingTurn(
  input: z.input<typeof researchPendingTurnCreationSchema>,
  {
    createId = () => globalThis.crypto.randomUUID(),
    now = () => new Date().toISOString(),
  }: {
    createId?: () => string;
    now?: () => string;
  } = {},
) {
  const parsed = researchPendingTurnCreationSchema.parse(input);
  const idempotencyKey = parsed.idempotency_key ?? createId();
  const userMessageId = parsed.user_message_id ?? createId();
  return researchPendingTurnInputSchema.parse({
    session_id: parsed.session_id,
    idempotency_key: idempotencyKey,
    turn: {
      schema_version: "1",
      id: userMessageId,
      user_message: {
        schema_version: "1",
        id: userMessageId,
        event_id: parsed.event_id ?? null,
        role: "user",
        content: parsed.content,
        created_at: parsed.created_at ?? now(),
      },
      assistant_message: null,
      run: null,
    },
  });
}

type ResearchTurnPages = InfiniteData<
  AskTurnList,
  unknown
>;

export class ResearchTurnConflictError extends Error {
  readonly code:
    | "IDEMPOTENCY_KEY_CONFLICT"
    | "PERSISTED_TURN_CONFLICT"
    | "TURN_ID_CONFLICT";

  constructor(
    code:
      | "IDEMPOTENCY_KEY_CONFLICT"
      | "PERSISTED_TURN_CONFLICT"
      | "TURN_ID_CONFLICT",
  ) {
    super(code);
    this.name = "ResearchTurnConflictError";
    this.code = code;
  }
}

function recordsKey(ownerId: string, sessionId: string) {
  return researchWorkspaceKeys.turnReconciliations(
    ownerId,
    sessionId,
  );
}

function getRecords(
  queryClient: QueryClient,
  ownerId: string,
  sessionId: string,
) {
  return z
    .array(researchTurnReconciliationSchema)
    .parse(
      queryClient.getQueryData(recordsKey(ownerId, sessionId)) ?? [],
    );
}

function setRecords(
  queryClient: QueryClient,
  ownerId: string,
  sessionId: string,
  records: readonly ResearchTurnReconciliation[],
) {
  const parsed = z
    .array(researchTurnReconciliationSchema)
    .parse(records);
  queryClient.setQueryData(
    recordsKey(ownerId, sessionId),
    parsed,
  );
}

function turnAnchorTime(turn: AskTurn) {
  return (
    turn.user_message?.created_at ??
    turn.assistant_message?.created_at ??
    ""
  );
}

function sortedRecords(
  records: readonly ResearchTurnReconciliation[],
) {
  return [...records].sort(
    (left, right) =>
      turnAnchorTime(left.turn).localeCompare(
        turnAnchorTime(right.turn),
      ) ||
      left.idempotency_key.localeCompare(right.idempotency_key),
  );
}

function sameOptimisticInput(
  record: ResearchTurnReconciliation,
  input: ResearchPendingTurnInput,
) {
  return (
    record.session_id === input.session_id &&
    JSON.stringify(record.turn) === JSON.stringify(input.turn)
  );
}

function findCachedTurn(
  queryClient: QueryClient,
  ownerId: string,
  sessionId: string,
  turnId: string,
) {
  for (const [, data] of queryClient.getQueriesData<ResearchTurnPages>({
    queryKey: researchWorkspaceKeys.turnsRoot(
      ownerId,
      sessionId,
    ),
  })) {
    for (const page of data?.pages ?? []) {
      const found = page.items.find((turn) => turn.id === turnId);
      if (found !== undefined) return found;
    }
  }
  return undefined;
}

function validatePersistedMatch(
  record: ResearchTurnReconciliation,
  persisted: AskTurn,
) {
  const optimisticUser = record.turn.user_message;
  if (
    optimisticUser === null ||
    persisted.id !== record.turn.id ||
    persisted.user_message === null ||
    persisted.user_message.id !== optimisticUser.id ||
    persisted.user_message.content !== optimisticUser.content ||
    persisted.user_message.event_id !== optimisticUser.event_id
  ) {
    throw new ResearchTurnConflictError(
      "PERSISTED_TURN_CONFLICT",
    );
  }
  const optimisticAssistant = record.turn.assistant_message;
  if (
    optimisticAssistant !== null &&
    persisted.assistant_message?.id !== optimisticAssistant.id
  ) {
    throw new ResearchTurnConflictError(
      "PERSISTED_TURN_CONFLICT",
    );
  }
}

function upsertPersistedTurn(
  data: ResearchTurnPages | undefined,
  persisted: AskTurn,
): {
  data: ResearchTurnPages;
  retained: boolean;
} {
  if (data === undefined || data.pages.length === 0) {
    return {
      data: {
        pages: [
          {
            schema_version: "1",
            items: [persisted],
            next_cursor: null,
          },
        ],
        pageParams: [null],
      },
      retained: true,
    };
  }

  let replaced = false;
  const pages = data.pages.map((page) => {
    const items = page.items.flatMap((turn) => {
      if (turn.id !== persisted.id) return [turn];
      if (replaced) return [];
      replaced = true;
      return [persisted];
    });
    return {
      ...page,
      items,
    };
  });

  const finalPageComplete =
    pages.at(-1)?.next_cursor === null;
  if (!replaced && finalPageComplete) {
    const lastPage = pages.at(-1);
    if (lastPage !== undefined) {
      pages[pages.length - 1] = {
        ...lastPage,
        items: [...lastPage.items, persisted],
      };
    }
  }

  return {
    data: {
      ...data,
      pages,
    },
    retained: replaced || finalPageComplete,
  };
}

function updatePersistedTurnCaches(
  queryClient: QueryClient,
  ownerId: string,
  sessionId: string,
  persisted: AskTurn,
) {
  const turnsRoot = researchWorkspaceKeys.turnsRoot(
    ownerId,
    sessionId,
  );
  const cachedQueries =
    queryClient.getQueriesData<ResearchTurnPages>({
      queryKey: turnsRoot,
    });
  if (cachedQueries.length === 0) {
    const result = upsertPersistedTurn(undefined, persisted);
    queryClient.setQueryData(
      researchWorkspaceKeys.turns(ownerId, sessionId),
      result.data,
    );
    return result.retained;
  }
  let retainedEverywhere = true;
  for (const [queryKey, data] of cachedQueries) {
    const result = upsertPersistedTurn(data, persisted);
    queryClient.setQueryData(
      queryKey,
      result.data,
    );
    retainedEverywhere &&= result.retained;
  }
  return retainedEverywhere;
}

export function mergeResearchTurns(
  data: ResearchTurnPages | undefined,
  records: readonly ResearchTurnReconciliation[],
) {
  const turns = data?.pages.flatMap((page) => page.items) ?? [];
  const byId = new Map(turns.map((turn) => [turn.id, turn]));
  for (const record of records) {
    const overlay =
      record.state === "synced"
        ? record.resolved_turn
        : record.turn;
    if (overlay !== null && !byId.has(overlay.id)) {
      byId.set(overlay.id, overlay);
    }
  }
  return [...byId.values()].sort(
    (left, right) =>
      turnAnchorTime(left).localeCompare(turnAnchorTime(right)) ||
      left.id.localeCompare(right.id),
  );
}

export function createResearchTurnReconciler({
  queryClient,
  ownerId,
  sessionId,
  enabled = true,
}: {
  queryClient: QueryClient;
  ownerId: string;
  sessionId: string;
  enabled?: boolean;
}) {
  function assertEnabled() {
    if (!enabled || ownerId.length === 0 || sessionId.length === 0) {
      throw new Error("Research turn reconciliation is disabled");
    }
  }

  function begin(input: ResearchPendingTurnInput) {
    assertEnabled();
    const parsed = researchPendingTurnInputSchema.parse(input);
    if (parsed.session_id !== sessionId) {
      throw new ResearchTurnConflictError("TURN_ID_CONFLICT");
    }
    const records = getRecords(queryClient, ownerId, sessionId);
    const existing = records.find(
      (record) =>
        record.idempotency_key === parsed.idempotency_key,
    );
    if (existing !== undefined) {
      if (!sameOptimisticInput(existing, parsed)) {
        throw new ResearchTurnConflictError(
          "IDEMPOTENCY_KEY_CONFLICT",
        );
      }
      return existing;
    }
    if (
      records.some((record) => record.turn.id === parsed.turn.id)
    ) {
      throw new ResearchTurnConflictError("TURN_ID_CONFLICT");
    }

    const alreadyPersisted = findCachedTurn(
      queryClient,
      ownerId,
      sessionId,
      parsed.turn.id,
    );
    const record = researchTurnReconciliationSchema.parse({
      schema_version: "1",
      session_id: sessionId,
      idempotency_key: parsed.idempotency_key,
      state: alreadyPersisted !== undefined ? "synced" : "saving",
      turn: parsed.turn,
      safe_error_code: null,
      persisted_turn_id: alreadyPersisted !== undefined
        ? parsed.turn.id
        : null,
      resolved_turn: null,
    });
    setRecords(
      queryClient,
      ownerId,
      sessionId,
      sortedRecords([...records, record]),
    );
    return record;
  }

  function reconcile(
    idempotencyKey: string,
    persistedTurn: AskTurn,
  ) {
    assertEnabled();
    const persisted = askTurnSchema.parse(persistedTurn);
    const records = getRecords(queryClient, ownerId, sessionId);
    const record = records.find(
      (candidate) =>
        candidate.idempotency_key === idempotencyKey,
    );
    if (record === undefined) {
      throw new ResearchTurnConflictError(
        "IDEMPOTENCY_KEY_CONFLICT",
      );
    }
    validatePersistedMatch(record, persisted);
    const retained = updatePersistedTurnCaches(
      queryClient,
      ownerId,
      sessionId,
      persisted,
    );
    const synced = researchTurnReconciliationSchema.parse({
      ...record,
      state: "synced",
      safe_error_code: null,
      persisted_turn_id: persisted.id,
      resolved_turn: retained ? null : persisted,
    });
    setRecords(
      queryClient,
      ownerId,
      sessionId,
      records.map((candidate) =>
        candidate.idempotency_key === idempotencyKey
          ? synced
          : candidate,
      ),
    );
    return synced;
  }

  function markUnsynced(
    idempotencyKey: string,
    errorCode: string,
  ) {
    assertEnabled();
    const parsedErrorCode = z
      .string()
      .regex(safeErrorCode)
      .parse(errorCode);
    const records = getRecords(queryClient, ownerId, sessionId);
    let updated: ResearchTurnReconciliation | undefined;
    const nextRecords = records.map((record) => {
      if (record.idempotency_key !== idempotencyKey) return record;
      if (record.state === "synced") {
        throw new ResearchTurnConflictError(
          "PERSISTED_TURN_CONFLICT",
        );
      }
      updated = researchTurnReconciliationSchema.parse({
        ...record,
        state: "unsynced",
        safe_error_code: parsedErrorCode,
        persisted_turn_id: null,
        resolved_turn: null,
      });
      return updated;
    });
    if (updated === undefined) {
      throw new ResearchTurnConflictError(
        "IDEMPOTENCY_KEY_CONFLICT",
      );
    }
    setRecords(
      queryClient,
      ownerId,
      sessionId,
      nextRecords,
    );
    return updated;
  }

  function retry(idempotencyKey: string) {
    assertEnabled();
    const records = getRecords(queryClient, ownerId, sessionId);
    let updated: ResearchTurnReconciliation | undefined;
    const nextRecords = records.map((record) => {
      if (record.idempotency_key !== idempotencyKey) return record;
      if (record.state === "synced") {
        updated = record;
        return record;
      }
      updated = researchTurnReconciliationSchema.parse({
        ...record,
        state: "saving",
        safe_error_code: null,
        persisted_turn_id: null,
        resolved_turn: null,
      });
      return updated;
    });
    if (updated === undefined) {
      throw new ResearchTurnConflictError(
        "IDEMPOTENCY_KEY_CONFLICT",
      );
    }
    setRecords(
      queryClient,
      ownerId,
      sessionId,
      nextRecords,
    );
    return updated;
  }

  return {
    begin,
    reconcile,
    markUnsynced,
    retry,
    records: () => getRecords(queryClient, ownerId, sessionId),
  } as const;
}

export function useResearchTurnReconciler(
  sessionId: string | null | undefined,
) {
  const queryClient = useQueryClient();
  const scope = useResearchWorkspaceScope();
  const stableSessionId = sessionId ?? "";
  const ownerId = scope.ownerId ?? "";
  return useMemo(
    () =>
      createResearchTurnReconciler({
        queryClient,
        ownerId,
        sessionId: stableSessionId,
        enabled:
          scope.enabled &&
          ownerId.length > 0 &&
          stableSessionId.length > 0,
      }),
    [
      ownerId,
      queryClient,
      scope.enabled,
      stableSessionId,
    ],
  );
}

export function useResearchTurnReconciliations(
  sessionId: string | null | undefined,
) {
  const scope = useResearchWorkspaceScope();
  const ownerId = scope.ownerId ?? "";
  const stableSessionId = sessionId ?? "";
  return useQuery({
    queryKey: researchWorkspaceKeys.turnReconciliations(
      ownerId,
      stableSessionId,
    ),
    queryFn: async () => [] as ResearchTurnReconciliation[],
    enabled:
      scope.enabled &&
      ownerId.length > 0 &&
      stableSessionId.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });
}

export function useResearchTurnsWithPending(
  sessionId: string | null | undefined,
  options: {
    enabled?: boolean;
    limit?: number;
  } = {},
) {
  const persisted = useResearchTurns(sessionId, options);
  const reconciliations =
    useResearchTurnReconciliations(sessionId);
  const turns = useMemo(
    () =>
      mergeResearchTurns(
        persisted.data,
        reconciliations.data ?? [],
      ),
    [persisted.data, reconciliations.data],
  );
  return {
    ...persisted,
    turns,
    reconciliations: reconciliations.data ?? [],
  };
}
