"use client";

import { Clapperboard, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { addShot, cancelProject, createCharacter, regenerateShot, selectShotVersion, submitShot } from "~/actions/projects";
import { resumeProduction } from "~/actions/productions";
import type { Character, Project, Shot } from "~/actions/projects";
import { generateProject } from "~/actions/director";
import { repurposeAsShorts } from "~/actions/workflows";
import type { CatalogModel } from "~/actions/models";
import type { BrandKit } from "~/actions/brand-kits";
import { ExportsSection } from "~/components/projects/exports-section";
import { ProductionDagPanel } from "~/components/projects/production-dag-panel";
import { ProductionBudgetPanel } from "~/components/projects/production-budget-panel";
import { FileDropInput } from "~/components/file-drop-input";
import { PlanReview } from "~/components/projects/plan-review";
import { ProductionProgress } from "~/components/projects/production-progress";
import { StudioEditor } from "~/components/projects/studio-editor";
import { ProjectStatusBadge, ShotStatusBadge } from "~/components/projects/status-badges";
import { Button } from "~/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { useDirectUpload } from "~/hooks/use-direct-upload";
import { useProjectPoll } from "~/hooks/use-project-poll";
import { cn } from "~/lib/utils";

// gap-closure: matches backend/app/core/constants.py::ProjectStatus —
// only these states are actually cancellable server-side (see
// MovieService.cancel_project).
const CANCELLABLE_PROJECT_STATUSES = new Set(["draft", "planning", "awaiting_approval", "generating", "assembling"]);

export function ProjectDetail({ project: initialProject, models }: { project: Project & { shots: Shot[]; characters: Character[] }; models: CatalogModel[]; brandKits?: BrandKit[] }) {
  const router = useRouter();
  // gap-closure: previously this page fetched once server-side with no
  // polling at all, despite ProductionProgress claiming "This updates
  // automatically — no need to refresh". See hooks/use-project-poll.ts.
  const project = useProjectPoll(initialProject);

  // The AI Director path (POST /plan) leaves the project here, with a plan
  // stored but no shots created yet \u2014 review/edit before anything is
  // created, matching spec section 53. Projects created the manual way
  // (the "New project" dialog on /projects) never enter this state.
  if (project.status === "awaiting_approval" && project.production_plan) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <ProjectStatusBadge status={project.status} />
        </div>
        <PlanReview projectId={project.id} initialPlan={project.production_plan} models={models} characters={project.characters} />
      </div>
    );
  }

  const hasShots = project.shots.length > 0;
  const shotGroups = (() => {
    const groups = new Map<string, { label: string; sceneNumber: number | null; shots: Shot[] }>();
    for (const shot of [...project.shots].sort((a, b) => a.order_index - b.order_index)) {
      const sceneNumber = shot.scene_number ?? null;
      const key = sceneNumber === null ? `manual-${shot.id}` : `scene-${sceneNumber}`;
      const group = groups.get(key) ?? { label: sceneNumber === null ? `Clip ${shot.order_index + 1}` : `Scene ${sceneNumber}`, sceneNumber, shots: [] };
      group.shots.push(shot);
      groups.set(key, group);
    }
    return [...groups.values()];
  })();
  const showProgress = hasShots || ["generating", "assembling", "ready", "failed"].includes(project.status);

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold">{project.title}</h1>
          {project.description && <p className="text-muted-foreground mt-1 text-sm">{project.description}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ProjectStatusBadge status={project.status} />
          {CANCELLABLE_PROJECT_STATUSES.has(project.status) && <CancelProjectButton projectId={project.id} />}
        </div>
      </div>

      {showProgress && <ProductionProgress status={project.status} shots={project.shots} />}
      {hasShots && (
        <StudioEditor
          projectId={project.id}
          projectTitle={project.title}
          shots={project.shots}
          outputUrl={project.output_url ?? null}
          aspectRatio={project.aspect_ratio ?? "16:9"}
          initialTimeline={project.editor_timeline ?? null}
        />
      )}

      {project.current_production_id && (project.status === "failed" || project.shots.some((shot) => shot.status === "failed")) && (
        <ResumeProductionButton productionId={project.current_production_id} />
      )}
      {showProgress && project.current_production_id && (
        <>
          <ProductionBudgetPanel productionId={project.current_production_id} />
          <ProductionDagPanel productionId={project.current_production_id} active={["generating", "assembling"].includes(project.status)} />
        </>
      )}

      {project.status === "generating" && project.shots.some((s) => s.status === "pending") && (
        <GenerateNowButton projectId={project.id} />
      )}

      {project.status === "ready" && project.output_url && (
        <div className="space-y-3">
          <video src={project.output_url} controls className="w-full rounded-xl border" />
          <RepurposeButton projectId={project.id} />
        </div>
      )}
      {project.status === "failed" && project.error_message && (
        <p className="text-destructive rounded-lg border p-3 text-sm">{project.error_message}</p>
      )}

      {project.status === "ready" && <ExportsSection projectId={project.id} />}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Characters</h2>
          <AddCharacterDialog onCreated={() => router.refresh()} projectId={project.id} />
        </div>
        {project.characters.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            No characters added yet. Add one to keep a consistent identity across shots.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {project.characters.map((c) => (
              <span key={c.id} className="bg-muted rounded-full px-3 py-1 text-xs">
                {c.name}
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Shots</h2>
          <AddShotDialog projectId={project.id} characters={project.characters} />
        </div>
        {project.shots.length === 0 ? (
          <div className="text-muted-foreground rounded-xl border py-10 text-center text-sm">
            No shots yet. Add one to start building this video.
          </div>
        ) : (
          <div className="space-y-3">
            {shotGroups.map((group, groupIndex) => {
              const plannedSeconds = group.shots.reduce((sum, shot) => sum + (shot.timeline_duration_seconds ?? shot.duration_seconds), 0);
              return (
                <details key={`${group.label}-${groupIndex}`} open={groupIndex === 0} className="group rounded-xl border bg-card">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                    <span className="text-sm font-medium">{group.label}</span>
                    <span className="text-muted-foreground text-xs">{group.shots.length} clip{group.shots.length === 1 ? "" : "s"} · {plannedSeconds}s timeline</span>
                  </summary>
                  <div className="space-y-2 border-t p-3">
                    {group.shots.map((shot) => (
                      <ShotRow key={shot.id} projectId={project.id} productionId={project.current_production_id} shot={shot} />
                    ))}
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function CancelProjectButton({ projectId }: { projectId: string }) {
  const [cancelling, setCancelling] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function onCancel() {
    setCancelling(true);
    try {
      await cancelProject(projectId);
      toast.success("Project cancelled \u2014 any unspent credits were refunded.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't cancel this project.");
    } finally {
      setCancelling(false);
      setConfirming(false);
    }
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-1">
        <Button size="sm" variant="destructive" onClick={() => void onCancel()} disabled={cancelling}>
          {cancelling ? "Cancelling\u2026" : "Confirm cancel"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={cancelling}>
          Never mind
        </Button>
      </div>
    );
  }

  return (
    <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
      Cancel
    </Button>
  );
}

function GenerateNowButton({ projectId }: { projectId: string }) {
  const [submitting, setSubmitting] = useState(false);

  async function onGenerate() {
    setSubmitting(true);
    try {
      await generateProject(projectId);
      toast.success("Generation started.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't start generation.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Button onClick={() => void onGenerate()} disabled={submitting}>
      {submitting ? "Starting\u2026" : "Generate now"}
    </Button>
  );
}

function ResumeProductionButton({ productionId }: { productionId: string }) {
  const router = useRouter();
  const [resuming, setResuming] = useState(false);
  const [resumed, setResumed] = useState(false);
  async function onResume() {
    setResuming(true);
    try {
      const result = await resumeProduction(productionId);
      toast.success(`Resumed production. ${result.retried_shot_ids.length} failed shot(s) queued; completed clips were preserved.`);
      setResumed(true);
      router.refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't resume this production.");
    } finally {
      setResuming(false);
    }
  }
  if (resumed) return null;
  return (
    <div className="border-destructive/20 bg-destructive/[0.03] flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium">Production paused after a failure</p>
        <p className="text-muted-foreground mt-1 text-xs">Retry failed shots and dependent work only. Completed clips and their existing charges stay untouched.</p>
      </div>
      <Button onClick={() => void onResume()} disabled={resuming}>
        {resuming ? "Resuming…" : "Resume production"}
      </Button>
    </div>
  );
}

function RepurposeButton({ projectId }: { projectId: string }) {
  const [submitting, setSubmitting] = useState(false);

  async function onRepurpose() {
    setSubmitting(true);
    try {
      const result = await repurposeAsShorts(projectId);
      toast.success(`Created ${result.clips.length} short clip${result.clips.length === 1 ? "" : "s"}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't generate shorts from this video.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={() => void onRepurpose()} disabled={submitting}>
      <Clapperboard className="size-4" />
      {submitting ? "Finding highlights\u2026" : "Repurpose as Shorts"}
    </Button>
  );
}

function ShotRow({ projectId, productionId, shot }: { projectId: string; productionId: string | null; shot: Shot }) {
  const [submitting, setSubmitting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [retryQueued, setRetryQueued] = useState(false);

  async function onSubmit() {
    setSubmitting(true);
    try {
      await submitShot(projectId, shot.id);
      toast.success("Shot submitted.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't submit that shot.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onRegenerate() {
    setRegenerating(true);
    try {
      if (shot.status === "failed" && productionId) {
        const result = await resumeProduction(productionId, shot.id);
        setRetryQueued(true);
        toast.success(`Retried ${result.retried_shot_ids.length} dependent failed shot(s); completed clips were preserved.`);
      } else {
        await regenerateShot(projectId, shot.id);
        toast.success("Regenerating a new version — your previous version is kept.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't regenerate that shot.");
    } finally {
      setRegenerating(false);
    }
  }

  const canRegenerate = shot.status === "completed" || shot.status === "failed";
  const allVersions = [...shot.generation_history, ...(shot.generation_id ? [shot.generation_id] : [])];
  const versionCount = allVersions.length;
  const [showVersions, setShowVersions] = useState(false);

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm">{shot.prompt}</p>
          <p className="text-muted-foreground text-xs">
            {shot.timeline_duration_seconds != null && Math.abs(shot.timeline_duration_seconds - shot.duration_seconds) > 0.01
              ? `${shot.timeline_duration_seconds}s timeline · ${shot.duration_seconds}s generated`
              : `${shot.duration_seconds}s`}
            {shot.continuity_mode && shot.continuity_mode !== "none" ? ` · ${shot.continuity_mode.replaceAll("_", " ")}` : ""}
            {shot.camera_notes ? ` · ${shot.camera_notes}` : ""}
            {versionCount > 1 ? ` · v${versionCount}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ShotStatusBadge status={shot.status} />
          {shot.status === "pending" && (
            <Button size="sm" variant="outline" onClick={() => void onSubmit()} disabled={submitting}>
              {submitting ? "Submitting\u2026" : "Submit"}
            </Button>
          )}
          {canRegenerate && (
            <Button size="sm" variant="outline" onClick={() => void onRegenerate()} disabled={regenerating || retryQueued}>
              {regenerating ? "Starting…" : retryQueued ? "Retry queued" : shot.status === "failed" && productionId ? "Retry shot" : "Regenerate"}
            </Button>
          )}
          {/* gap-closure: POST /shots/{id}/select-version has worked on
              the backend since scene versioning shipped (migration
              0004_scene_versioning.py) — there was simply no UI for it. */}
          {versionCount > 1 && (
            <Button size="sm" variant="ghost" onClick={() => setShowVersions((v) => !v)}>
              {showVersions ? "Hide versions" : `${versionCount} versions`}
            </Button>
          )}
        </div>
      </div>
      {showVersions && versionCount > 1 && (
        <VersionBrowser projectId={projectId} shot={shot} versions={allVersions} onClose={() => setShowVersions(false)} />
      )}
    </div>
  );
}

function VersionBrowser({
  projectId,
  shot,
  versions,
  onClose,
}: {
  projectId: string;
  shot: Shot;
  versions: string[];
  onClose: () => void;
}) {
  const [selecting, setSelecting] = useState<string | null>(null);

  async function onSelect(generationId: string) {
    setSelecting(generationId);
    try {
      await selectShotVersion(projectId, shot.id, generationId);
      toast.success("Switched to that version.");
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't switch to that version.");
    } finally {
      setSelecting(null);
    }
  }

  return (
    <div className="flex flex-wrap gap-2 border-t pt-2">
      {versions.map((generationId, i) => {
        const isCurrent = generationId === shot.generation_id;
        return (
          <Button
            key={generationId}
            size="sm"
            variant={isCurrent ? "default" : "outline"}
            disabled={isCurrent || selecting !== null}
            onClick={() => void onSelect(generationId)}
          >
            v{i + 1}
            {isCurrent ? " (current)" : selecting === generationId ? "\u2026" : ""}
          </Button>
        );
      })}
    </div>
  );
}

function AddCharacterDialog({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: (c: Character) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const { upload, uploading } = useDirectUpload();

  async function onCreate() {
    if (!name.trim() || files.length === 0) {
      toast.error("A name and at least one reference image are required.");
      return;
    }
    setSubmitting(true);
    try {
      const keys = await Promise.all(files.map((f) => upload(f, "characterReference")));
      const character = await createCharacter(projectId, { name, reference_s3_keys: keys });
      onCreated(character);
      setOpen(false);
      setName("");
      setFiles([]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't create that character.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Plus className="size-4" />
          Add character
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add character</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Character name" maxLength={120} />
          <FileDropInput
            accept="image/*"
            label="Reference photo (up to 6 can be added via the backend; one at a time here)"
            preview="image"
            onFile={(f) => setFiles(f ? [f] : [])}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => void onCreate()} disabled={busy}>
            {uploading ? "Uploading\u2026" : submitting ? "Creating\u2026" : "Add character"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddShotDialog({ projectId, characters }: { projectId: string; characters: Character[] }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [cameraNotes, setCameraNotes] = useState("");
  const [duration, setDuration] = useState(5);
  const [selectedCharacters, setSelectedCharacters] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  function toggleCharacter(id: string) {
    setSelectedCharacters((prev) => (prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]));
  }

  async function onCreate() {
    if (!prompt.trim()) {
      toast.error("Describe the shot first.");
      return;
    }
    setSubmitting(true);
    try {
      await addShot(projectId, {
        prompt,
        camera_notes: cameraNotes || undefined,
        duration_seconds: duration,
        character_ids: selectedCharacters,
      });
      setOpen(false);
      setPrompt("");
      setCameraNotes("");
      setSelectedCharacters([]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't add that shot.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          Add shot
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add shot</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe this shot\u2026" rows={3} maxLength={2000} />
          <Input value={cameraNotes} onChange={(e) => setCameraNotes(e.target.value)} placeholder="Camera notes (optional)" maxLength={500} />
          <div>
            <p className="mb-2 text-xs font-medium">Duration</p>
            <div className="flex flex-wrap gap-2">
              {[3, 5, 8, 10, 15].map((d) => (
                <button
                  key={d}
                  onClick={() => setDuration(d)}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-sm transition-colors",
                    duration === d ? "border-foreground bg-foreground text-background" : "border-border hover:border-foreground/40",
                  )}
                >
                  {d}s
                </button>
              ))}
            </div>
          </div>
          {characters.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium">Characters in this shot</p>
              <div className="flex flex-wrap gap-2">
                {characters.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => toggleCharacter(c.id)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs transition-colors",
                      selectedCharacters.includes(c.id)
                        ? "border-foreground bg-foreground text-background"
                        : "border-border hover:border-foreground/40",
                    )}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={() => void onCreate()} disabled={submitting}>
            {submitting ? "Adding\u2026" : "Add shot"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
