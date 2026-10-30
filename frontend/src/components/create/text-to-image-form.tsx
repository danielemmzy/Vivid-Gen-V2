"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { textToImage, type GenerationResult } from "~/actions/generation";
import type { CatalogModel } from "~/actions/models";
import { useGenerationEstimate } from "~/hooks/use-generation-estimate";
import { GenerationEstimateCard } from "~/components/create/generation-estimate-card";
import { GenerationResultPanel } from "~/components/generation-result-panel";
import { Button } from "~/components/ui/button";
import { Textarea } from "~/components/ui/textarea";
import { cn } from "~/lib/utils";

const ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"];
const QUALITY = [
  { id: "low", label: "Low", hint: "Fast & economical" },
  { id: "medium", label: "Medium", hint: "Best balance" },
  { id: "high", label: "High", hint: "Highest quality" },
] as const;

export function TextToImageForm({ models }: { models: CatalogModel[] }) {
  const searchParams = useSearchParams();
  const [prompt, setPrompt] = useState(searchParams.get("prompt") ?? "");
  const [quality, setQuality] = useState<(typeof QUALITY)[number]["id"]>("medium");
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [numImages, setNumImages] = useState(1);
  const [modelChoice, setModelChoice] = useState("auto");
  const [submitting, setSubmitting] = useState(false);
  const availableModels = models.filter((model) => model.provider_configured);
  const { estimate, loading: estimateLoading, error: estimateError } = useGenerationEstimate({
    generation_type: "text_to_image", model_id: modelChoice === "auto" ? undefined : modelChoice,
    quality_mode: quality, aspect_ratio: aspectRatio, num_images: numImages,
  });
  const [result, setResult] = useState<GenerationResult | null>(null);

  async function onSubmit() {
    if (!prompt.trim()) { toast.error("Write a prompt first."); return; }
    if (!estimate || estimateLoading || estimateError) { toast.error("Wait for a valid cost estimate before generating."); return; }
    setSubmitting(true);
    try {
      setResult(await textToImage({ prompt, model: estimate.model_id, quality_mode: quality, aspect_ratio: aspectRatio, num_images: numImages }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed to start.");
    } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-5">
      <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the image you want…" rows={4} maxLength={5000} />
      <QualityPicker value={quality} onChange={setQuality} />
      <label className="block space-y-2"><span className="text-xs font-medium">Model</span><select value={modelChoice} onChange={(event) => setModelChoice(event.target.value)} className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"><option value="auto">Auto · recommended for this quality</option>{availableModels.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.quality_tier ?? "standard"}</option>)}</select></label>
      <ChoiceRow label="Aspect ratio" options={ASPECT_RATIOS} value={aspectRatio} onChange={setAspectRatio} />
      <ChoiceRow label="Number of images" options={["1", "2", "3", "4"]} value={String(numImages)} onChange={(v) => setNumImages(Number(v))} />
      <GenerationEstimateCard estimate={estimate} loading={estimateLoading} error={estimateError} />
      <div className="flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">The quote is free to check. Credits are reserved only when you generate.</p><Button onClick={() => void onSubmit()} disabled={submitting || estimateLoading || !estimate || !!estimateError || !prompt.trim()} className="rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">{submitting ? "Generating…" : estimateLoading ? "Updating estimate…" : estimate ? `Generate · ${estimate.credits_to_reserve} credits` : "Generate image"}</Button></div>
      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}

export function QualityPicker({ value, onChange }: { value: "low" | "medium" | "high"; onChange: (v: "low" | "medium" | "high") => void }) {
  return <div><p className="mb-2 text-xs font-medium">Quality</p><div className="grid grid-cols-3 gap-2">{QUALITY.map((q) => <button key={q.id} onClick={() => onChange(q.id)} className={cn("rounded-md border px-3 py-2 text-left transition-colors", value === q.id ? "border-primary bg-primary/[0.07] text-foreground shadow-[inset_0_0_0_1px_rgba(215,46,60,0.10)]" : "border-border hover:border-primary/35")}><span className="block text-sm font-medium">{q.label}</span><span className="block text-xs opacity-70">{q.hint}</span></button>)}</div><p className="mt-2 text-xs text-muted-foreground">Vivid automatically selects the best available model for this quality level.</p></div>;
}

function ChoiceRow({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (v: string) => void }) {
  return <div><p className="mb-2 text-xs font-medium">{label}</p><div className="flex flex-wrap gap-2">{options.map((opt) => <button key={opt} onClick={() => onChange(opt)} className={cn("rounded-md border px-3 py-1.5 text-sm transition-colors", value === opt ? "border-primary bg-primary/[0.07] text-foreground shadow-[inset_0_0_0_1px_rgba(215,46,60,0.10)]" : "border-border hover:border-primary/35")}>{opt}</button>)}</div></div>;
}
