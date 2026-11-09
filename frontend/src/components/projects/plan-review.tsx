"use client";

import { ArrowDown, ArrowUp, Copy, Eye, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  approvePlan,
  type ProductionPlan,
  type ScenePlan,
} from "~/actions/director";
import type { Character } from "~/actions/projects";
import { BackendError } from "~/lib/backend";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { estimateCredits } from "~/lib/pricing";
import type { CatalogModel } from "~/actions/models";
import { cn } from "~/lib/utils";

function isSceneExecutable(scene: ScenePlan): boolean {
  if (
    scene.visual_type === "generated_video" ||
    scene.visual_type === "user_asset"
  )
    return true;
  if (
    scene.visual_type === "stock_video" ||
    scene.visual_type === "stock_image"
  )
    return Boolean(scene.stock_source_url);
  return false;
}

function renumberScenes(scenes: ScenePlan[]): ScenePlan[] {
  return scenes.map((scene, index) => ({ ...scene, scene_number: index + 1 }));
}

const VISUAL_TYPES: { value: ScenePlan["visual_type"]; label: string }[] = [
  { value: "generated_video", label: "AI-generated video" },
  { value: "generated_image", label: "AI-generated image" },
  { value: "user_asset", label: "Use my uploaded media" },
  { value: "stock_video", label: "Use a stock video URL" },
  { value: "stock_image", label: "Use a stock image URL" },
  { value: "text_graphic", label: "Text / graphic" },
];

export function PlanReview({
  projectId,
  initialPlan,
  models,
  characters,
}: {
  projectId: string;
  initialPlan: ProductionPlan;
  models: CatalogModel[];
  characters: Character[];
}) {
  const router = useRouter();
  const [plan, setPlan] = useState<ProductionPlan>(initialPlan);
  const [approving, setApproving] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);

  function updateScene(index: number, patch: Partial<ScenePlan>) {
    setPlan((prev) => {
      const oldScene = prev.scenes[index];
      const nextScenes = prev.scenes.map((scene, i) =>
        i === index ? { ...scene, ...patch } : scene,
      );
      const durationChange =
        patch.duration_seconds !== undefined && oldScene
          ? patch.duration_seconds - oldScene.duration_seconds
          : 0;
      return {
        ...prev,
        duration_seconds: Math.max(1, prev.duration_seconds + durationChange),
        scenes: nextScenes,
      };
    });
  }

  function moveScene(index: number, direction: -1 | 1) {
    setPlan((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.scenes.length) return prev;
      const next = [...prev.scenes];
      [next[index], next[target]] = [next[target]!, next[index]!];
      return { ...prev, scenes: renumberScenes(next) };
    });
  }

  function duplicateScene(index: number) {
    setPlan((prev) => {
      const source = prev.scenes[index];
      if (!source) return prev;
      const copy = { ...source, purpose: `${source.purpose} (copy)` };
      return {
        ...prev,
        duration_seconds: prev.duration_seconds + copy.duration_seconds,
        scenes: renumberScenes([
          ...prev.scenes.slice(0, index + 1),
          copy,
          ...prev.scenes.slice(index + 1),
        ]),
      };
    });
  }

  function addScene() {
    const newScene: ScenePlan = {
      scene_number: plan.scenes.length + 1,
      duration_seconds: 5,
      purpose: "New scene",
      visual_type: "generated_video",
      visual_prompt: "Describe what the viewer should see in this scene.",
      voiceover_line: null,
      camera_notes: null,
      requires_character_reference: false,
      requires_product_reference: false,
      character_id: null,
      source_asset_s3_key: null,
      stock_source_url: null,
    };
    setPlan((prev) => ({
      ...prev,
      duration_seconds: prev.duration_seconds + newScene.duration_seconds,
      scenes: renumberScenes([...prev.scenes, newScene]),
    }));
  }

  function deleteScene(index: number) {
    setPlan((prev) => {
      if (prev.scenes.length <= 1) return prev;
      const removed = prev.scenes[index];
      return {
        ...prev,
        duration_seconds: Math.max(
          1,
          prev.duration_seconds - (removed?.duration_seconds ?? 0),
        ),
        scenes: renumberScenes(prev.scenes.filter((_, i) => i !== index)),
      };
    });
  }

  const estimatedTotalCredits = plan.scenes
    .filter((scene) => scene.visual_type === "generated_video")
    .reduce((sum, scene) => {
      const needsImageInput = Boolean(
        scene.character_id ??
        scene.requires_character_reference ??
        scene.requires_product_reference,
      );
      const capability = needsImageInput ? "image_to_video" : "text_to_video";
      const model = models.find((candidate) => {
        if (candidate.type !== capability || !candidate.supports_movie_shots)
          return false;
        if (plan.video_engine === "wan") return candidate.provider === "modal";
        if (plan.video_engine === "kling")
          return candidate.id.startsWith("kling-2.5-turbo-pro");
        return true;
      });
      return sum + (model ? estimateCredits(model, scene.duration_seconds) : 0);
    }, 0);

  async function onApprove() {
    setApproving(true);
    setValidationErrors([]);
    try {
      await approvePlan(projectId, plan);
      router.push(`/projects/${projectId}`);
      router.refresh();
    } catch (err) {
      if (err instanceof BackendError && Array.isArray(err.details?.errors)) {
        setValidationErrors(err.details.errors as string[]);
      } else {
        toast.error(
          err instanceof Error ? err.message : "Couldn't approve this plan.",
        );
      }
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="space-y-5">
      <header className="bg-card rounded-2xl border p-4 sm:p-6">
        <p className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
          Your storyboard
        </p>
        <h2 className="font-display text-xl font-semibold sm:text-2xl">
          {plan.title}
        </h2>
        <p className="text-muted-foreground mt-2 text-sm">
          {plan.duration_seconds}s video <span className="mx-1">·</span>{" "}
          {plan.aspect_ratio} <span className="mx-1">·</span>{" "}
          {plan.scenes.length} scenes
          {plan.target_platform ? (
            <>
              <span className="mx-1">·</span>
              {plan.target_platform.replaceAll("_", " ")}
            </>
          ) : null}
        </p>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm">
          Start with the scene titles and descriptions. Everything else is
          optional. You can preview this plan for free before making any video.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="bg-background rounded-xl border p-3">
            <p className="text-xs font-semibold">1. Edit scenes</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Change what happens in each shot.
            </p>
          </div>
          <div className="bg-background rounded-xl border p-3">
            <p className="text-xs font-semibold">2. Preview for free</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Review the storyboard; no video is generated.
            </p>
          </div>
          <div className="bg-background rounded-xl border p-3">
            <p className="text-xs font-semibold">3. Generate when ready</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Credits are used only when you start generation.
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-1 text-xs font-semibold">
            Video engine
            <select
              value={plan.video_engine ?? "auto"}
              onChange={(e) => {
                const videoEngine = e.target.value as "auto" | "wan" | "kling";
                setPlan((p) => ({ ...p, video_engine: videoEngine }));
              }}
              className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2.5 text-sm font-normal"
            >
              <option value="auto">Automatic (recommended)</option>
              <option value="wan">WAN 2.2 — Modal (self-hosted)</option>
              <option value="kling">Kling 2.5 — fal.ai (managed)</option>
            </select>
            <span className="text-muted-foreground block font-normal">
              Your choice is preferred; if unavailable, Vivid may fall back to
              another configured engine.
            </span>
          </label>
          <label className="space-y-1 text-xs font-semibold">
            Video quality
            <select
              value={plan.quality_mode}
              onChange={(e) =>
                setPlan((p) => ({
                  ...p,
                  quality_mode: e.target
                    .value as ProductionPlan["quality_mode"],
                }))
              }
              className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2.5 text-sm font-normal"
            >
              <option value="low">Fast / lower cost</option>
              <option value="medium">Balanced (recommended)</option>
              <option value="high">Higher quality</option>
            </select>
            <span className="text-muted-foreground block font-normal">
              In Automatic mode, this guides model routing. A selected engine
              takes priority.
            </span>
          </label>
          <label className="space-y-1 text-xs font-semibold">
            Output resolution
            <select
              value={plan.resolution}
              onChange={(e) =>
                setPlan((p) => ({ ...p, resolution: e.target.value }))
              }
              className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2.5 text-sm font-normal"
            >
              <option value="420p">420p — draft</option>
              <option value="720p">720p — HD</option>
              <option value="1080p">1080p — Full HD</option>
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setPreviewOpen((open) => !open)}
          >
            <Eye className="mr-2 size-4" />
            {previewOpen ? "Hide free preview" : "Preview storyboard for free"}
          </Button>
          <span className="text-muted-foreground text-xs">
            Previewing and approving the plan do not generate video or spend
            generation credits.
          </span>
        </div>
        <details className="mt-4 rounded-xl border px-3 py-2.5">
          <summary className="cursor-pointer text-sm font-medium select-none">
            Video settings{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </summary>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs font-medium">
              Video shape
              <select
                value={plan.aspect_ratio}
                onChange={(e) =>
                  setPlan((p) => ({ ...p, aspect_ratio: e.target.value }))
                }
                className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2 text-sm font-normal"
              >
                <option value="16:9">Landscape (16:9)</option>
                <option value="9:16">Vertical (9:16)</option>
                <option value="1:1">Square (1:1)</option>
                <option value="4:5">Portrait (4:5)</option>
              </select>
            </label>
            <label className="space-y-1 text-xs font-medium">
              Visual style
              <Input
                value={plan.style ?? ""}
                onChange={(e) =>
                  setPlan((p) => ({ ...p, style: e.target.value || null }))
                }
                placeholder="e.g. cinematic, anime, realistic"
                className="mt-1 font-normal"
              />
            </label>
            <label className="space-y-1 text-xs font-medium">
              Audience
              <Input
                value={plan.audience ?? ""}
                onChange={(e) =>
                  setPlan((p) => ({ ...p, audience: e.target.value || null }))
                }
                placeholder="Who is this video for?"
                className="mt-1 font-normal"
              />
            </label>
            <label className="space-y-1 text-xs font-medium">
              Language
              <Input
                value={plan.language}
                onChange={(e) =>
                  setPlan((p) => ({ ...p, language: e.target.value }))
                }
                placeholder="e.g. English"
                className="mt-1 font-normal"
              />
            </label>
            <label className="space-y-1 text-xs font-medium">
              Platform
              <select
                value={plan.target_platform ?? "none"}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    target_platform:
                      e.target.value === "none" ? null : e.target.value,
                  }))
                }
                className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2 text-sm font-normal"
              >
                <option value="none">Any platform</option>
                <option value="instagram_reels">Instagram Reels</option>
                <option value="tiktok">TikTok</option>
                <option value="youtube">YouTube</option>
                <option value="youtube_shorts">YouTube Shorts</option>
              </select>
            </label>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 rounded-lg border p-3 text-sm">
              <input
                type="checkbox"
                checked={plan.voiceover.enabled}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    voiceover: { ...p.voiceover, enabled: e.target.checked },
                  }))
                }
              />{" "}
              Add voiceover
            </label>
            <label className="flex items-center gap-2 rounded-lg border p-3 text-sm">
              <input
                type="checkbox"
                checked={plan.music.enabled}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    music: { ...p.music, enabled: e.target.checked },
                  }))
                }
              />{" "}
              Add background music
            </label>
            <label className="flex items-center gap-2 rounded-lg border p-3 text-sm">
              <input
                type="checkbox"
                checked={plan.captions.enabled}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    captions: { ...p.captions, enabled: e.target.checked },
                  }))
                }
              />{" "}
              Add captions
            </label>
            <label className="flex items-center gap-2 rounded-lg border p-3 text-sm">
              <input
                type="checkbox"
                checked={plan.branding.enabled}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    branding: { ...p.branding, enabled: e.target.checked },
                  }))
                }
              />{" "}
              Include brand kit
            </label>
          </div>
          {plan.music.enabled && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs font-medium">
                Music mood
                <Input
                  value={plan.music.mood ?? ""}
                  onChange={(e) =>
                    setPlan((p) => ({
                      ...p,
                      music: { ...p.music, mood: e.target.value || null },
                    }))
                  }
                  placeholder="e.g. uplifting"
                  className="mt-1 font-normal"
                />
              </label>
              <label className="space-y-1 text-xs font-medium">
                Music genre
                <Input
                  value={plan.music.genre ?? ""}
                  onChange={(e) =>
                    setPlan((p) => ({
                      ...p,
                      music: { ...p.music, genre: e.target.value || null },
                    }))
                  }
                  placeholder="e.g. electronic"
                  className="mt-1 font-normal"
                />
              </label>
            </div>
          )}
          {plan.captions.enabled && (
            <label className="mt-3 block space-y-1 text-xs font-medium">
              Caption style
              <Input
                value={plan.captions.style}
                onChange={(e) =>
                  setPlan((p) => ({
                    ...p,
                    captions: { ...p.captions, style: e.target.value },
                  }))
                }
                placeholder="e.g. clean, bold"
                className="mt-1 font-normal"
              />
            </label>
          )}
        </details>
      </header>

      {previewOpen && (
        <section
          className="bg-card rounded-2xl border p-4 sm:p-6"
          aria-label="Free storyboard preview"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold">Storyboard preview</h3>
              <p className="text-muted-foreground mt-1 text-sm">
                This is a planning preview only. It does not call a video
                provider and uses no generation credits.
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPreviewOpen(false)}
            >
              Close preview
            </Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {plan.scenes.map((scene, index) => (
              <article
                key={`preview-${index}`}
                className="rounded-xl border p-4"
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="bg-muted rounded-full px-2.5 py-1 text-xs font-semibold">
                    Scene {index + 1}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {scene.duration_seconds}s
                  </span>
                </div>
                <h4 className="font-semibold">
                  {scene.purpose || `Scene ${index + 1}`}
                </h4>
                <p className="text-muted-foreground mt-2 text-sm whitespace-pre-wrap">
                  {scene.visual_prompt || "No visual description yet."}
                </p>
                {scene.voiceover_line && (
                  <p className="mt-3 border-t pt-3 text-sm">
                    <span className="font-medium">Voiceover: </span>
                    {scene.voiceover_line}
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {validationErrors.length > 0 && (
        <div className="border-destructive/50 bg-destructive/5 space-y-1 rounded-lg border p-3">
          <p className="text-destructive text-xs font-medium">
            A few things need fixing:
          </p>
          <ul className="text-destructive list-inside list-disc text-xs">
            {validationErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {plan.script && (
        <details className="bg-card rounded-xl border px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium select-none">
            View full script{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </summary>
          <p className="text-muted-foreground mt-3 text-sm leading-6 whitespace-pre-wrap">
            {plan.script}
          </p>
        </details>
      )}

      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">Scenes</h3>
          <p className="text-muted-foreground text-xs">
            Each card is one part of your video.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={addScene}>
          <Plus className="mr-1.5 size-4" /> Add scene
        </Button>
      </div>

      <div className="space-y-3">
        {plan.scenes.map((scene, index) => (
          <article
            key={`${scene.scene_number}-${index}`}
            className="bg-card overflow-hidden rounded-xl border"
          >
            <div className="bg-muted/30 flex items-start gap-3 border-b p-3 sm:p-4">
              <div className="bg-background flex size-9 shrink-0 items-center justify-center rounded-lg border text-sm font-semibold">
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <Input
                  aria-label={`Scene ${index + 1} title`}
                  value={scene.purpose}
                  onChange={(e) =>
                    updateScene(index, { purpose: e.target.value })
                  }
                  className="h-9 border-0 bg-transparent px-1 text-sm font-semibold shadow-none focus-visible:ring-1"
                  placeholder="What happens in this scene?"
                />
                <p className="text-muted-foreground mt-1 px-1 text-xs">
                  {scene.duration_seconds} seconds
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-0.5">
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  disabled={index === 0}
                  onClick={() => moveScene(index, -1)}
                  aria-label="Move scene earlier"
                  title="Move earlier"
                >
                  <ArrowUp className="size-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  disabled={index === plan.scenes.length - 1}
                  onClick={() => moveScene(index, 1)}
                  aria-label="Move scene later"
                  title="Move later"
                >
                  <ArrowDown className="size-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  onClick={() => duplicateScene(index)}
                  aria-label="Duplicate scene"
                  title="Duplicate"
                >
                  <Copy className="size-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  disabled={plan.scenes.length <= 1}
                  onClick={() => deleteScene(index)}
                  aria-label="Delete scene"
                  title="Delete"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-3 p-3 sm:p-4">
              <label className="block space-y-1.5 text-xs font-medium">
                Describe what we see
                <Textarea
                  value={scene.visual_prompt}
                  onChange={(e) =>
                    updateScene(index, { visual_prompt: e.target.value })
                  }
                  rows={3}
                  maxLength={5000}
                  className="text-sm font-normal"
                  placeholder="Describe the action, setting, people, and mood…"
                />
              </label>
              {!isSceneExecutable(scene) && (
                <p className="text-warning text-xs">
                  This scene needs extra setup before it can be created. Open
                  More options below.
                </p>
              )}
              <details className="rounded-lg border px-3 py-2.5">
                <summary className="cursor-pointer text-sm font-medium select-none">
                  More options{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </summary>
                <div className="mt-3 space-y-3">
                  <label className="block space-y-1 text-xs font-medium">
                    Scene type
                    <select
                      value={scene.visual_type}
                      onChange={(e) =>
                        updateScene(index, {
                          visual_type: e.target
                            .value as ScenePlan["visual_type"],
                        })
                      }
                      className="bg-background border-input mt-1 w-full rounded-md border px-3 py-2 text-sm font-normal"
                    >
                      {VISUAL_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>
                          {type.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-1 text-xs font-medium">
                    Duration (seconds)
                    <Input
                      type="number"
                      min={1}
                      max={30}
                      value={scene.duration_seconds}
                      onChange={(e) => {
                        const value = Number(e.target.value);
                        if (Number.isFinite(value) && value >= 1 && value <= 30)
                          updateScene(index, { duration_seconds: value });
                      }}
                      className="font-normal"
                    />
                  </label>
                  {(scene.visual_type === "stock_video" ||
                    scene.visual_type === "stock_image") && (
                    <label className="block space-y-1 text-xs font-medium">
                      Direct media URL
                      <Input
                        type="url"
                        value={scene.stock_source_url ?? ""}
                        onChange={(e) =>
                          updateScene(index, {
                            stock_source_url: e.target.value || null,
                          })
                        }
                        placeholder="https://…"
                        className="font-normal"
                      />
                    </label>
                  )}
                  <label className="block space-y-1 text-xs font-medium">
                    Voiceover line{" "}
                    <span className="text-muted-foreground font-normal">
                      (optional)
                    </span>
                    <Textarea
                      value={scene.voiceover_line ?? ""}
                      onChange={(e) =>
                        updateScene(index, {
                          voiceover_line: e.target.value || null,
                        })
                      }
                      rows={2}
                      placeholder="Words spoken during this scene"
                      className="font-normal"
                    />
                  </label>
                  <label className="block space-y-1 text-xs font-medium">
                    Camera notes{" "}
                    <span className="text-muted-foreground font-normal">
                      (optional)
                    </span>
                    <Textarea
                      value={scene.camera_notes ?? ""}
                      onChange={(e) =>
                        updateScene(index, {
                          camera_notes: e.target.value || null,
                        })
                      }
                      rows={2}
                      placeholder="e.g. slow push-in, wide shot"
                      className="font-normal"
                    />
                  </label>
                  {characters.length > 0 &&
                    (scene.requires_character_reference ||
                      scene.requires_product_reference ||
                      scene.character_id) && (
                      <div>
                        <p className="mb-2 text-xs font-medium">
                          {scene.requires_product_reference
                            ? "Product reference"
                            : "Character reference"}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              updateScene(index, { character_id: null })
                            }
                            className={cn(
                              "rounded-full border px-3 py-1.5 text-xs transition-colors",
                              !scene.character_id
                                ? "border-foreground bg-foreground text-background"
                                : "hover:border-foreground/40",
                            )}
                          >
                            None
                          </button>
                          {characters.map((character) => (
                            <button
                              type="button"
                              key={character.id}
                              onClick={() =>
                                updateScene(index, {
                                  character_id: character.id,
                                })
                              }
                              className={cn(
                                "rounded-full border px-3 py-1.5 text-xs transition-colors",
                                scene.character_id === character.id
                                  ? "border-foreground bg-foreground text-background"
                                  : "hover:border-foreground/40",
                              )}
                            >
                              {character.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                </div>
              </details>
            </div>
          </article>
        ))}
      </div>

      <footer className="bg-background/95 sticky bottom-3 z-10 rounded-xl border p-3 shadow-lg backdrop-blur sm:flex sm:items-center sm:justify-between sm:gap-4 sm:p-4">
        <div className="mb-3 sm:mb-0">
          <p className="text-sm font-medium">Ready to make your video?</p>
          <p className="text-muted-foreground mt-1 text-xs">
            {estimatedTotalCredits !== null
              ? `Estimated ${estimatedTotalCredits} credits for AI video scenes · final cost may vary`
              : "Credit estimate unavailable"}
          </p>
        </div>
        <Button
          onClick={() => void onApprove()}
          disabled={approving}
          className="w-full sm:w-auto"
        >
          {approving ? "Preparing your scenes…" : "Looks good — continue"}
        </Button>
      </footer>
      <p className="text-muted-foreground text-center text-xs">
        Continuing creates your shots. Only the final Generate action uses
        video-generation credits.
      </p>
    </div>
  );
}
