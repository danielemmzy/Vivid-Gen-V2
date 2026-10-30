"use client";

import { useState } from "react";
import { toast } from "sonner";
import { imageToImage, type GenerationResult } from "~/actions/generation";
import type { CatalogModel } from "~/actions/models";
import { useGenerationEstimate } from "~/hooks/use-generation-estimate";
import { GenerationEstimateCard } from "~/components/create/generation-estimate-card";
import { FileDropInput } from "~/components/file-drop-input";
import { GenerationResultPanel } from "~/components/generation-result-panel";
import { Button } from "~/components/ui/button";
import { Textarea } from "~/components/ui/textarea";
import { useDirectUpload } from "~/hooks/use-direct-upload";
import { cn } from "~/lib/utils";

const QUALITY = [{ id: "low", label: "Low", hint: "Fast edit" }, { id: "medium", label: "Medium", hint: "Balanced" }, { id: "high", label: "High", hint: "Premium edit" }] as const;

export function ImageToImageForm({ models }: { models: CatalogModel[] }) {
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [quality, setQuality] = useState<(typeof QUALITY)[number]["id"]>("medium");
  const [modelChoice, setModelChoice] = useState("auto");
  const [submitting, setSubmitting] = useState(false);
  const availableModels = models.filter((model) => model.provider_configured);
  const { estimate, loading: estimateLoading, error: estimateError } = useGenerationEstimate({
    generation_type: "image_to_image", model_id: modelChoice === "auto" ? undefined : modelChoice, quality_mode: quality,
  });
  const [result, setResult] = useState<GenerationResult | null>(null);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a source image first.");
      return;
    }
    if (!prompt.trim()) {
      toast.error("Describe the edit you want.");
      return;
    }
    if (!estimate || estimateLoading || estimateError) { toast.error("Wait for a valid cost estimate before generating."); return; }
    setSubmitting(true);
    try {
      const input_s3_key = await upload(file, "imageToImageSource");
      const generation = await imageToImage({ prompt, input_s3_key, model: estimate.model_id, quality_mode: quality });
      setResult(generation);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed to start.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <div className="space-y-5">
      <FileDropInput accept="image/*" label="Drop an image, or click to browse" preview="image" onFile={setFile} />
      <Textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe the change you want\u2026"
        rows={3}
        maxLength={5000}
      />
      <div>
        <p className="mb-2 text-xs font-medium">Quality</p>
        <div className="grid grid-cols-3 gap-2">{QUALITY.map((q) => <button key={q.id} onClick={() => setQuality(q.id)} className={cn("rounded-md border px-3 py-2 text-left", quality === q.id ? "border-primary bg-primary/[0.07] text-foreground shadow-[inset_0_0_0_1px_rgba(215,46,60,0.10)]" : "border-border hover:border-primary/35")}><span className="block text-sm font-medium">{q.label}</span><span className="block text-xs opacity-70">{q.hint}</span></button>)}</div>
      </div>
      <label className="block space-y-2"><span className="text-xs font-medium">Model</span><select value={modelChoice} onChange={(event) => setModelChoice(event.target.value)} className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"><option value="auto">Auto · recommended for this quality</option>{availableModels.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.quality_tier ?? "standard"}</option>)}</select></label>
      <GenerationEstimateCard estimate={estimate} loading={estimateLoading} error={estimateError} />
      <div className="flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">No credits are spent by checking the estimate.</p><Button onClick={() => void onSubmit()} disabled={busy || estimateLoading || !estimate || !!estimateError || !prompt.trim() || !file} className="rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">{uploading ? "Uploading…" : submitting ? "Generating…" : estimateLoading ? "Updating estimate…" : estimate ? `Generate · ${estimate.credits_to_reserve} credits` : "Generate image"}</Button></div>
      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}
