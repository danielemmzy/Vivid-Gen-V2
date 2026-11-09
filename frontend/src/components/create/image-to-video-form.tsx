"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createPlan } from "~/actions/director";
import { createCharacter, createProject } from "~/actions/projects";
import { FileDropInput } from "~/components/file-drop-input";
import { Button } from "~/components/ui/button";
import { Textarea } from "~/components/ui/textarea";
import { useDirectUpload } from "~/hooks/use-direct-upload";

const DURATIONS = [15, 30, 45, 60, 90, 120];
const ASPECTS = ["16:9", "9:16", "1:1", "4:5"];

/** Image-led projects deliberately enter the same plan review/editor as text, URL and PPTX projects. */
export function ImageToVideoForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(30);
  const [resolution, setResolution] = useState("720p");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [submitting, setSubmitting] = useState(false);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a source image first.");
      return;
    }
    if (!prompt.trim()) {
      toast.error(
        "Describe the story or motion you want to create from this image.",
      );
      return;
    }
    setSubmitting(true);
    try {
      const imageKey = await upload(file, "imageToVideoSource");
      const cleanName = file.name
        .replace(/\.[^.]+$/, "")
        .replace(/[_-]+/g, " ")
        .trim();
      const project = await createProject({
        title: prompt.trim().slice(0, 80) || cleanName || "Image-led movie",
        description: `Image-led production · ${file.name}`,
        aspect_ratio: aspectRatio,
        resolution,
      });
      // The uploaded image becomes an explicit character/visual reference, rather than
      // being submitted directly to a one-shot generator and bypassing the editor.
      const referenceName = cleanName.slice(0, 60) || "Visual reference";
      await createCharacter(project.id, {
        name: referenceName,
        description: `Primary visual reference from uploaded image ${file.name}. Preserve its relevant identity, palette, wardrobe and environment where appropriate.`,
        reference_s3_keys: [imageKey],
      });
      await createPlan(project.id, {
        prompt: `${prompt.trim()}\n\nUse the uploaded image as the primary visual reference. Use the saved character named ${referenceName} and its image reference for scenes where it fits. Build a coherent multi-shot sequence; do not simply repeat the same composition. Preserve relevant identity, wardrobe, palette and environment while varying framing and camera movement. The user will review and edit the storyboard before generation.`,
        project_type: "image_to_video",
        duration_seconds: duration,
        aspect_ratio: aspectRatio,
        resolution,
        quality_mode: "balanced",
        style: "cinematic",
        source_facts: `Uploaded visual reference: ${file.name}. Reference asset key: ${imageKey}. Use the saved character reference for visual continuity; do not invent factual claims about the image beyond visible details.`,
      });
      toast.success(
        "Storyboard created. Review and edit it before generating.",
      );
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not create the image-led storyboard.",
      );
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;
  return (
    <div className="space-y-5">
      <section className="border-border/80 bg-card rounded-2xl border p-4 shadow-sm sm:p-6">
        <div className="mb-4 flex items-start gap-3">
          <span className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-xl">
            ✦
          </span>
          <div>
            <h2 className="font-display text-lg font-semibold">
              Start with a visual reference
            </h2>
            <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
              Your image becomes a saved reference for the storyboard. You can
              edit scenes, narration, captions, sound and branding before you
              approve production.
            </p>
          </div>
        </div>
        <FileDropInput
          accept="image/png,image/jpeg,image/webp"
          label="Drop a JPG, PNG or WebP image, or click to browse"
          preview="image"
          onFile={setFile}
        />
        <Textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Describe the story and movement: a slow cinematic push-in, then reveal the city skyline as the character turns toward the sunrise…"
          rows={4}
          maxLength={5000}
          className="bg-background mt-4 rounded-xl text-sm leading-relaxed"
        />
        <p className="text-muted-foreground mt-2 text-right text-[11px]">
          {prompt.length.toLocaleString()} / 5,000
        </p>
      </section>

      <section className="border-border/80 bg-card grid gap-4 rounded-2xl border p-4 sm:grid-cols-3 sm:p-5">
        <label className="space-y-2 text-xs font-semibold">
          <span className="text-muted-foreground tracking-[0.12em] uppercase">
            Finished movie
          </span>
          <select
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
            className="border-border bg-background h-11 w-full rounded-xl border px-3 text-sm font-medium"
          >
            {DURATIONS.map((value) => (
              <option key={value} value={value}>
                {value} seconds
              </option>
            ))}
          </select>
          <span className="text-muted-foreground block leading-relaxed font-normal">
            The planner creates multiple editable scenes to reach the target
            timeline.
          </span>
        </label>
        <label className="space-y-2 text-xs font-semibold">
          <span className="text-muted-foreground tracking-[0.12em] uppercase">
            Aspect ratio
          </span>
          <select
            value={aspectRatio}
            onChange={(event) => setAspectRatio(event.target.value)}
            className="border-border bg-background h-11 w-full rounded-xl border px-3 text-sm font-medium"
          >
            {ASPECTS.map((value) => (
              <option key={value} value={value}>
                {value}
                {value === "9:16"
                  ? " · vertical"
                  : value === "16:9"
                    ? " · landscape"
                    : ""}
              </option>
            ))}
          </select>
          <span className="text-muted-foreground block leading-relaxed font-normal">
            Choose framing for the intended destination.
          </span>
        </label>
        <label className="space-y-2 text-xs font-semibold">
          <span className="text-muted-foreground tracking-[0.12em] uppercase">
            Output resolution
          </span>
          <select
            value={resolution}
            onChange={(event) => setResolution(event.target.value)}
            className="border-border bg-background h-11 w-full rounded-xl border px-3 text-sm font-medium"
          >
            <option value="420p">420p · Economy output</option>
            <option value="720p">720p · HD</option>
          </select>
          <span className="text-muted-foreground block leading-relaxed font-normal">
            Final availability depends on the selected provider and render
            configuration.
          </span>
        </label>
      </section>

      <div className="border-border flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-muted-foreground max-w-lg text-xs leading-relaxed">
          No video generation starts here. First you review the shared
          storyboard and estimate, then approve shots and start production from
          the project workspace.
        </p>
        <Button
          onClick={() => void onSubmit()}
          disabled={busy}
          className="bg-primary text-primary-foreground hover:bg-primary/90 h-11 rounded-xl px-5 font-semibold shadow-[0_8px_20px_-12px_rgba(215,46,60,0.8)]"
        >
          {uploading
            ? "Uploading reference…"
            : submitting
              ? "Building storyboard…"
              : "Create editable storyboard"}
        </Button>
      </div>
    </div>
  );
}
