import type { JobState } from "@/lib/types";
import { Pill } from "@/components/ui";

export function JobStatus({ state }: { state?: JobState | null }) {
  if (!state) return <Pill>new</Pill>;
  if (state === "done") return <Pill tone="success">done</Pill>;
  if (state === "error") return <Pill tone="error">error</Pill>;
  if (state === "running") return <Pill tone="primary">running</Pill>;
  return <Pill tone="warn">queued</Pill>;
}
