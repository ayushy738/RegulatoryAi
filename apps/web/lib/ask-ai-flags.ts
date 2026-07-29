type AskAiPublicEnvironment = {
  NEXT_PUBLIC_ASK_AI_V2_UI_ENABLED?: string;
  VITE_ASK_AI_V2_UI_ENABLED?: string;
};

export function parseFeatureFlag(value: string | undefined): boolean {
  return value?.trim().toLowerCase() === "true";
}

export function resolveAskAiV2UiEnabled(
  environment: AskAiPublicEnvironment,
): boolean {
  return parseFeatureFlag(
    environment.NEXT_PUBLIC_ASK_AI_V2_UI_ENABLED ??
      environment.VITE_ASK_AI_V2_UI_ENABLED,
  );
}

const viteEnvironment =
  (import.meta as ImportMeta & { env?: AskAiPublicEnvironment }).env ?? {};

export const askAiV2UiEnabled = resolveAskAiV2UiEnabled({
  ...viteEnvironment,
  NEXT_PUBLIC_ASK_AI_V2_UI_ENABLED:
    typeof process === "undefined"
      ? undefined
      : process.env.NEXT_PUBLIC_ASK_AI_V2_UI_ENABLED,
});
