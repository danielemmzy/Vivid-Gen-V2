import { Badge } from "~/components/ui/badge";
import { cn } from "~/lib/utils";

// Verified against backend/app/core/constants.py::ProjectStatus and ShotStatus.
const PROJECT_STATUS: Record<string, { label: string; className: string }> = {
  draft: { label: "Draft", className: "text-muted-foreground" },
  // gap-closure: these two states (a project between POST /plan and POST
  // /approve-plan) and "cancelled" existed on the backend enum from the
  // start of the AI Director work but were never in this map — they'd
  // have silently fallen through to the generic `status` fallback below.
  planning: { label: "Planning", className: "text-warning" },
  awaiting_approval: { label: "Awaiting approval", className: "text-warning" },
  cancelled: { label: "Cancelled", className: "text-muted-foreground" },
  generating: { label: "Generating", className: "text-warning" },
  assembling: { label: "Assembling", className: "text-warning" },
  ready: { label: "Ready", className: "text-success" },
  failed: { label: "Failed", className: "text-destructive" },
};

const SHOT_STATUS: Record<string, { label: string; className: string }> = {
  pending: { label: "Not submitted", className: "text-muted-foreground" },
  queued: { label: "Queued", className: "text-muted-foreground" },
  processing: { label: "Processing", className: "text-warning" },
  completed: { label: "Completed", className: "text-success" },
  failed: { label: "Failed", className: "text-destructive" },
};

// gap-closure: used by hooks/use-project-poll.ts to decide when to keep
// polling GET /projects/{id} — mirrors isInFlight in
// generation-status-badge.tsx, kept as its own function since Project and
// Generation have genuinely different status enums.
export function isProjectInFlight(status: string) {
  return ["planning", "awaiting_approval", "generating", "assembling"].includes(status);
}

export function ProjectStatusBadge({ status }: { status: string }) {
  const meta = PROJECT_STATUS[status] ?? { label: status, className: "text-muted-foreground" };
  return (
    <Badge variant="outline" className={cn("font-normal", meta.className)}>
      {meta.label}
    </Badge>
  );
}

export function ShotStatusBadge({ status }: { status: string }) {
  const meta = SHOT_STATUS[status] ?? { label: status, className: "text-muted-foreground" };
  return (
    <Badge variant="outline" className={cn("font-normal", meta.className)}>
      {meta.label}
    </Badge>
  );
}
