import { stripMarkdownNoise } from "@/app/workspace/format";

export function MarkdownLite({ content }: { content: string }) {
  if (!content.trim()) {
    return <p className="muted">Ask a question to generate an analyst-style answer.</p>;
  }
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  return (
    <div className="markdown-lite">
      {lines.map((line, index) => {
        const clean = stripMarkdownNoise(line);
        if (/^\|/.test(line)) {
          return (
            <code key={`${line}-${index}`} className="markdown-code">
              {clean.replace(/\|/g, "  ")}
            </code>
          );
        }
        if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
          return (
            <p key={`${line}-${index}`} className="markdown-bullet">
              {clean}
            </p>
          );
        }
        if (/^#{1,6}\s+/.test(line)) {
          return <strong key={`${line}-${index}`}>{clean}</strong>;
        }
        return <p key={`${line}-${index}`}>{clean}</p>;
      })}
    </div>
  );
}
