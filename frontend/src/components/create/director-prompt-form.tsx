"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createProject } from "~/actions/projects";
import { createPlan } from "~/actions/director";
import type { CatalogModel } from "~/actions/models";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";

const PLATFORMS = [["none", "No specific platform"], ["instagram_reels", "Instagram Reels"], ["tiktok", "TikTok"], ["youtube", "YouTube"], ["youtube_shorts", "YouTube Shorts"]] as const;
const RATIOS = [["16:9", "16:9 · Landscape"], ["9:16", "9:16 · Vertical"], ["1:1", "1:1 · Square"], ["4:5", "4:5 · Portrait"]] as const;
const QUALITY = [["fast", "Fast draft", "Lowest cost · quick preview"], ["balanced", "Balanced", "Best default for most briefs"], ["best", "High quality", "More detail · higher cost"]] as const;
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="space-y-1.5 text-xs font-semibold"><span className="uppercase tracking-[0.12em] text-muted-foreground">{label}</span>{children}</label>; }

export function DirectorPromptForm({ initialPrompt = "", models = [] }: { initialPrompt?: string; models?: CatalogModel[] }) {
  const router = useRouter();
  const [prompt, setPrompt] = useState(initialPrompt); const [duration, setDuration] = useState(30); const [platform, setPlatform] = useState("none"); const [style, setStyle] = useState("cinematic"); const [aspectRatio, setAspectRatio] = useState("16:9"); const [resolution, setResolution] = useState("720p"); const [quality, setQuality] = useState("balanced"); const [modelId, setModelId] = useState("auto"); const [submitting, setSubmitting] = useState(false);
  const selected = useMemo(() => models.find((model) => model.id === modelId), [models, modelId]);
  async function onSubmit() {
    if (!prompt.trim()) { toast.error("Describe what you want to create."); return; } setSubmitting(true);
    try { const project = await createProject({ title: prompt.slice(0, 80), aspect_ratio: aspectRatio, resolution }); await createPlan(project.id, { prompt, duration_seconds: duration, aspect_ratio: aspectRatio, resolution, quality_mode: quality as "fast" | "balanced" | "best", model_id: modelId === "auto" ? undefined : modelId, target_platform: platform === "none" ? undefined : platform, style }); router.push(`/projects/${project.id}`); }
    catch (err) { toast.error(err instanceof Error ? err.message : "The AI Director couldn't plan this one."); setSubmitting(false); }
  }
  return <div className="neo-panel space-y-5 p-5">
    <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the story, subject, setting and ending…" rows={3} maxLength={5000} className="border-0 bg-transparent p-0 text-base shadow-none focus-visible:ring-0" />
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field label="Duration"><select value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="studio-select">{[15, 30, 45, 60, 90, 120].map((d) => <option key={d} value={d}>{d}s finished video</option>)}</select></Field>
      <Field label="Platform"><select value={platform} onChange={(e) => setPlatform(e.target.value)} className="studio-select">{PLATFORMS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <Field label="Aspect ratio"><select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="studio-select">{RATIOS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <Field label="Resolution"><select value={resolution} onChange={(e) => setResolution(e.target.value)} className="studio-select"><option value="420p">420p · Economy</option><option value="720p">720p · HD</option><option value="1080p">1080p · Pro</option></select></Field>
    </div>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><Field label="Visual style"><Input value={style} onChange={(e) => setStyle(e.target.value)} placeholder="cinematic, creator, corporate…" className="h-10 rounded-xl" /></Field><Field label="Model engine"><select value={modelId} onChange={(e) => setModelId(e.target.value)} className="studio-select"><option value="auto">Auto · best fit for this brief</option>{models.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.quality_tier ?? "standard"}</option>)}</select></Field></div>
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">{QUALITY.map(([value, label, hint]) => <button key={value} type="button" onClick={() => setQuality(value)} className={`rounded-xl border px-3 py-2.5 text-left transition ${quality === value ? "border-primary bg-primary/[0.08] shadow-[inset_0_0_0_1px_rgba(215,46,60,0.16)]" : "border-border hover:border-primary/40"}`}><span className="block text-sm font-semibold">{label}</span><span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span></button>)}</div>
    {selected && <div className="rounded-xl border border-border/80 bg-muted/30 px-3 py-2 text-xs text-muted-foreground"><strong className="text-foreground">{selected.name}</strong> · {selected.capabilities.duration_options?.length ? `${selected.capabilities.duration_options.join(", ")}s shots` : "provider-native duration"} · {selected.credits_per_unit} credits/{selected.unit}</div>}
    <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">Planning is free. You review the storyboard and model-aware estimate before any Fal generation starts.</p><Button onClick={() => void onSubmit()} disabled={submitting || !prompt.trim()} className="surface-gold">{submitting ? "Planning…" : "Plan my video"}</Button></div>
  </div>;
}
