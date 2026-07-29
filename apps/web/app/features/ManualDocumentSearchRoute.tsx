import { ResearchWorkspaceDataProvider } from "@/lib/ask-ai-data";

import { ManualDocumentSearch } from "./ask-ai/ManualDocumentSearch";

export function ManualDocumentSearchRoute() {
  return (
    <ResearchWorkspaceDataProvider enabled>
      <ManualDocumentSearch />
    </ResearchWorkspaceDataProvider>
  );
}
