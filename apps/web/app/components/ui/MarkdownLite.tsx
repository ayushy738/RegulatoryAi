import type { ReactNode } from "react";

import { cleanText, stripMarkdownNoise } from "@/app/workspace/format";

type Block =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "code"; text: string }
  | { type: "table"; rows: string[][] };

function parseTableRow(line: string) {
  return line
    .split("|")
    .map((cell) => cell.trim())
    .filter(Boolean);
}

function isTableDivider(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function parseBlocks(content: string): Block[] {
  const rawLines = content.split(/\r?\n/);
  const blocks: Block[] = [];
  let index = 0;

  while (index < rawLines.length) {
    const line = rawLines[index] ?? "";
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < rawLines.length && !rawLines[index]?.trim().startsWith("```")) {
        code.push(rawLines[index] ?? "");
        index += 1;
      }
      blocks.push({ type: "code", text: code.join("\n") });
      index += 1;
      continue;
    }

    if (/^\|/.test(trimmed)) {
      const rows: string[][] = [];
      while (index < rawLines.length && /^\|/.test(rawLines[index]?.trim() ?? "")) {
        const row = rawLines[index]?.trim() ?? "";
        if (!isTableDivider(row)) rows.push(parseTableRow(row));
        index += 1;
      }
      if (rows.length) blocks.push({ type: "table", rows });
      continue;
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      blocks.push({ type: "heading", text: stripMarkdownNoise(trimmed) });
      index += 1;
      continue;
    }

    if (/^([-*]|\d+\.)\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < rawLines.length && /^([-*]|\d+\.)\s+/.test(rawLines[index]?.trim() ?? "")) {
        items.push(stripMarkdownNoise((rawLines[index] ?? "").replace(/^([-*]|\d+\.)\s+/, "")));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    const paragraph = [trimmed];
    index += 1;
    while (
      index < rawLines.length &&
      rawLines[index]?.trim() &&
      !/^#{1,6}\s+/.test(rawLines[index]?.trim() ?? "") &&
      !/^([-*]|\d+\.)\s+/.test(rawLines[index]?.trim() ?? "") &&
      !/^\|/.test(rawLines[index]?.trim() ?? "") &&
      !rawLines[index]?.trim().startsWith("```")
    ) {
      paragraph.push(rawLines[index]?.trim() ?? "");
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  return cleanText(text, "")
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .filter(Boolean)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={`${part}-${index}`}>{cleanText(part.slice(2, -2), "")}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
      }
      return <span key={`${part}-${index}`}>{part}</span>;
    });
}

export function MarkdownLite({ content }: { content: string }) {
  if (!content.trim()) {
    return <p className="muted">Ask a question to generate an analyst-style answer.</p>;
  }
  const blocks = parseBlocks(content);
  return (
    <div className="markdown-lite premium-markdown">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return <h3 key={`${block.text}-${index}`}>{renderInline(block.text)}</h3>;
        }
        if (block.type === "list") {
          return (
            <ul key={`${block.items.join("-")}-${index}`}>
              {block.items.map((item) => (
                <li key={item}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "code") {
          return (
            <pre key={`${block.text}-${index}`}>
              <code>{block.text}</code>
            </pre>
          );
        }
        if (block.type === "table") {
          const [head, ...body] = block.rows;
          return (
            <div className="markdown-table-wrap" key={`${index}-${head?.join("-")}`}>
              <table>
                {head ? (
                  <thead>
                    <tr>
                      {head.map((cell) => (
                        <th key={cell}>{renderInline(cell)}</th>
                      ))}
                    </tr>
                  </thead>
                ) : null}
                <tbody>
                  {body.map((row, rowIndex) => (
                    <tr key={`${row.join("-")}-${rowIndex}`}>
                      {row.map((cell) => (
                        <td key={cell}>{renderInline(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return <p key={`${block.text}-${index}`}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}
