"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { createPlan } from "~/actions/director";
import { createProject } from "~/actions/projects";
import { Button } from "~/components/ui/button";
import { Textarea } from "~/components/ui/textarea";

const DURATIONS = [15, 30, 45, 60, 90, 120, 180, 300, 600];

/** Text-to-video shares the same editable movie plan and render gate as every source-based workflow. */
export function TextToVideoForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [prompt, setPrompt] = useState(searchParams.get("prompt") ?? "");
  const [duration, setDuration] = useState(30);
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [resolution, setResolution] = useState("720p");
  const [quality, setQuality] = useState("balanced");
  const [style, setStyle] = useState("cinematic");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!prompt.trim()) { toast.error("Write a brief for your movie first."); return; }
    setSubmitting(true);
    try {
      const project = await createProject({ title: prompt.trim().slice(0, 80), description: "Text-led movie storyboard", aspect_ratio: aspectRatio, resolution });
      await createPlan(project.id, {
        prompt: `${prompt.trim()}\n\nPlan this as a complete finished movie, not one long inference. Create a coherent sequence of editable scenes and shots with continuity across the story.`,
        project_type: "video",
        duration_seconds: duration,
        aspect_ratio: aspectRatio,
        resolution,
        quality_mode: quality as "low" | "medium" | "high" | "fast" | "balanced" | "best",
        style: style || undefined,
      });
      // Preserve quality preference in the first editable plan via a URL-free editor handoff.
      // PlanReview remains the single approval gate for credit-spending production.
      toast.success("Storyboard ready. Review scenes and the cost estimate before production.");
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create the storyboard.");
      setSubmitting(false);
    }
  }

  return <div className="space-y-5">
    <section className="rounded-2xl border border-border/80 bg-card p-4 shadow-sm sm:p-6"><div className="mb-4 flex items-start gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">✦</span><div><h2 className="font-display text-lg font-semibold">Describe the movie you want</h2><p className="mt-1 text-sm leading-relaxed text-muted-foreground">The Director turns your brief into a multi-scene storyboard. Nothing renders until you review and approve the editable plan.</p></div></div><Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="A cinematic short film about a courier crossing a rain-soaked futuristic city to deliver a mysterious package. Start with a wide skyline, follow the courier through neon streets, build tension in a crowded market, and end at a quiet rooftop…" rows={5} maxLength={5000} className="min-h-36 resize-y rounded-xl border-border/90 bg-background text-sm leading-relaxed"/><div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground"><span>Include subject, action, setting, tone and ending.</span><span className="font-mono tabular-nums">{prompt.length.toLocaleString()} / 5,000</span></div></section>
    <section className="grid gap-4 rounded-2xl border border-border/80 bg-card p-4 shadow-sm sm:grid-cols-2 xl:grid-cols-5 sm:p-5"><label className="space-y-2 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">Finished duration</span><select value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm">{DURATIONS.map((value) => <option key={value} value={value}>{value >= 60 ? `${Math.floor(value / 60)}m${value % 60 ? ` ${value % 60}s` : ""}` : `${value}s`}</option>)}</select><span className="block font-normal text-muted-foreground">The planner creates enough scenes for the full timeline.</span></label><label className="space-y-2 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">Aspect ratio</span><select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"><option value="16:9">16:9 · Landscape</option><option value="9:16">9:16 · Vertical</option><option value="1:1">1:1 · Square</option><option value="4:5">4:5 · Portrait</option></select></label><label className="space-y-2 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">Resolution</span><select value={resolution} onChange={(e) => setResolution(e.target.value)} className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"><option value="420p">420p · Economy output</option><option value="720p">720p · HD</option></select></label><label className="space-y-2 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">Visual style</span><select value={style} onChange={(e) => setStyle(e.target.value)} className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"><option value="cinematic">Cinematic</option><option value="creator">Creator / social</option><option value="corporate">Corporate</option><option value="bold">Bold / graphic</option><option value="minimal">Minimal</option></select></label><label className="space-y-2 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">Quality profile</span><select value={quality} onChange={(e) => setQuality(e.target.value)} className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"><option value="fast">Fast draft</option><option value="balanced">Balanced</option><option value="best">High quality</option></select><span className="block font-normal text-muted-foreground">Final model support is validated during planning.</span></label></section>
    <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="max-w-lg text-xs leading-relaxed text-muted-foreground">The editor shows a model-aware credit estimate after planning. Approval creates shots without spending credits; generation starts only from the project workspace.</p><Button onClick={() => void onSubmit()} disabled={submitting || !prompt.trim()} className="h-11 rounded-xl bg-primary px-5 font-semibold text-primary-foreground shadow-[0_8px_20px_-12px_rgba(215,46,60,0.8)] hover:bg-primary/90">{submitting ? "Planning storyboard…" : "Create editable storyboard"}</Button></div>
  </div>;
}
