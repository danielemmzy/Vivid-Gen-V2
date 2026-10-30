import { Badge } from "~/components/ui/badge";
import { cn } from "~/lib/utils";

/**
 * Renders the REAL backend states verified in
 * backend/app/core/constants.py::GenerationStatus. Do not add a status here
 * that the backend doesn't emit, and do not collapse two backend states
 * into one label — "reserving_credits" and "processing" look similar to a
 * user but are genuinely different backend phases and a stuck reservation
 * is a different failure mode than a stuck provider call.
 */
const STATUS_META: Record<string, { label: string; dot: string; className: string }> = {
  queued: { label: "Queued", dot: "bg-muted-foreground", className: "text-muted-foreground" },
  reserving_credits: { label: "Reserving credits", dot: "bg-muted-foreground", className: "text-muted-foreground" },
  processing: { label: "Generating", dot: "bg-warning animate-pulse", className: "text-warning" },
  postprocessing: { label: "Finalizing", dot: "bg-warning animate-pulse", className: "text-warning" },
  completed: { label: "Ready", dot: "bg-success", className: "text-success" },
  failed: { label: "Failed", dot: "bg-destructive", className: "text-destructive" },
  refunded: { label: "Refunded", dot: "bg-muted-foreground", className: "text-muted-foreground" },
  // gap-closure: backend/app/core/constants.py::GenerationStatus.CANCELLED
  // — previously there was no way to reach this state at all (no cancel
  // endpoint existed), so the frontend never needed to render it.
  cancelled: { label: "Cancelled", dot: "bg-muted-foreground", className: "text-muted-foreground" },
};

export function isInFlight(status: string) {
  return !STATUS_META[status] || !["completed", "failed", "refunded", "cancelled"].includes(status);
}

export function GenerationStatusBadge({ status, className }: { status: string; className?: string }) {
  const meta = STATUS_META[status] ?? { label: status, dot: "bg-muted-foreground", className: "text-muted-foreground" };
  return (
    <Badge variant="outline" className={cn("gap-1.5 font-normal", meta.className, className)}>
      <span className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </Badge>
  );
}
