export interface DiffLine {
  kind: "add" | "remove" | "context";
  value: string;
}

export function createLineDiff(sourceText: string, targetText: string): DiffLine[] {
  const sourceLines = sourceText.split("\n");
  const targetLines = targetText.split("\n");
  const max = Math.max(sourceLines.length, targetLines.length);
  const lines: DiffLine[] = [];

  for (let index = 0; index < max; index += 1) {
    const sourceLine = sourceLines[index];
    const targetLine = targetLines[index];

    if (sourceLine === targetLine && sourceLine !== undefined) {
      lines.push({ kind: "context", value: sourceLine });
      continue;
    }

    if (sourceLine !== undefined) {
      lines.push({ kind: "remove", value: sourceLine });
    }

    if (targetLine !== undefined) {
      lines.push({ kind: "add", value: targetLine });
    }
  }

  return lines;
}
