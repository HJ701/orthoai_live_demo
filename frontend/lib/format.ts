export function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function percent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

export function seconds(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(value >= 10 ? 1 : 2)}s`;
}

export function displayClass(raw: unknown): string {
  const value = String(raw ?? "");
  const map: Record<string, string> = {
    "0": "Class I",
    "1": "Class II div 1",
    "2": "Class III",
  };
  return map[value] || value || "-";
}
