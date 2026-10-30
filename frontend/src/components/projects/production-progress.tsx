import { Check, Circle, Loader2 } from "lucide-react";
import type { Shot } from "~/actions/projects";
import { cn } from "~/lib/utils";

/**
 * A simple shot-completion summary bar. gap-closure (0007): the more
 * detailed claim this docstring used to make — that voice/music/
 * captions/branding weren't invoked by the generate flow at all — is no
 * longer true; the full DAG (SCENE/VOICE/CAPTIONS/MUSIC/BRANDING/RENDER
 * tasks, each with real status) is now real and rendered by
 * ProductionDagPanel just below this component. This bar stays as a
 * quick at-a-glance summary of shot completion; the DAG panel is where
 * to look for the full picture, including the non-scene steps this bar
 * intentionally doesn't try to represent.
 */
export function ProductionProgress({ status, shots }: { status: string; shots: Shot[] }) {
  const completed = shots.filter((s) => s.status === "completed").length;
  const failed = shots.filter((s) => s.status === "failed").length;
  const inProgress = shots.filter((s) => s.status === "processing" || s.status === "queued").length;
  const pending = shots.filter((s) => s.status === "pending").length;
  // Approval moves the project to "generating" immediately, before any
  // shot is actually submitted (that's the separate, explicit /generate
  // call — see project-detail.tsx's "Generate now" button). Don't show a
  // spinning "generating" step until something has actually started.
  const generationStarted = inProgress > 0 || completed > 0 || failed > 0;

  const steps: { label: string; state: "done" | "active" | "pending" }[] = [
    { label: "Storyboard planned", state: "done" }, // always true on this page — a plan exists to render this UI at all
    {
      label: `Clips created (${shots.length})`,
      state: shots.length > 0 ? "done" : "pending",
    },
    {
      label: generationStarted
        ? `Generating clips (${completed}/${shots.length} done${failed > 0 ? `, ${failed} failed` : ""})`
        : `Ready to generate (${pending} clip${pending === 1 ? "" : "s"})`,
      state: generationStarted ? (status === "generating" ? "active" : "done") : "pending",
    },
    {
      label: "Assembling final video",
      state: status === "assembling" ? "active" : status === "ready" ? "done" : "pending",
    },
    { label: "Ready", state: status === "ready" ? "done" : "pending" },
  ];

  return (
    <div className="space-y-2 rounded-lg border p-4">
      {steps.map((step) => (
        <div key={step.label} className="flex items-center gap-2 text-sm">
          {step.state === "done" ? (
            <Check className="text-success size-4 shrink-0" />
          ) : step.state === "active" ? (
            <Loader2 className="text-warning size-4 shrink-0 animate-spin" />
          ) : (
            <Circle className="text-muted-foreground size-4 shrink-0" />
          )}
          <span className={cn(step.state === "pending" && "text-muted-foreground")}>{step.label}</span>
        </div>
      ))}
      {inProgress > 0 && (
        <p className="text-muted-foreground pt-1 text-xs">This updates automatically \u2014 no need to refresh.</p>
      )}
    </div>
  );
}
