import {
  ResearchWorkspaceDataProvider,
} from "@/lib/ask-ai-data";

import {
  type ResearchSubmitCapability,
} from "./ask-ai/ResearchWorkspaceShell";
import { ResearchWorkspace } from "./ask-ai/ResearchWorkspace";

export function AskRoute({
  onResearchSubmit,
}: {
  onResearchSubmit?: ResearchSubmitCapability;
}) {
  return (
    <ResearchWorkspaceDataProvider enabled>
      <ResearchWorkspace onSubmit={onResearchSubmit} />
    </ResearchWorkspaceDataProvider>
  );
}
