"use client";

import { useState } from "react";
import { toast } from "sonner";
import { createAvatar, type GenerationResult } from "~/actions/generation";
import { GenerationEstimateCard } from "~/components/create/generation-estimate-card";
import { FileDropInput } from "~/components/file-drop-input";
import { GenerationResultPanel } from "~/components/generation-result-panel";
import { Button } from "~/components/ui/button";
import { useDirectUpload } from "~/hooks/use-direct-upload";
import { readMediaDuration } from "~/hooks/use-media-duration";
import { useGenerationEstimate } from "~/hooks/use-generation-estimate";

export function AvatarForm() {
  const [photo, setPhoto] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [audioDuration, setAudioDuration] = useState<number | null>(null);
  const [durationLoading, setDurationLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const { upload, uploading } = useDirectUpload();
  const { estimate, loading: estimateLoading, error: estimateError } = useGenerationEstimate(
    audio && !durationLoading ? {
      generation_type: "avatar",
      model_id: "omnihuman-1.5",
      duration_seconds: audioDuration ?? undefined,
    } : null,
  );

  async function chooseAudio(file: File | null) {
    setAudio(file);
    setAudioDuration(null);
    if (!file) return;
    setDurationLoading(true);
    try { setAudioDuration(await readMediaDuration(file)); }
    finally { setDurationLoading(false); }
  }

  async function onSubmit() {
    if (!photo || !audio) { toast.error("A photo and an audio track are both required."); return; }
    if (!estimate || estimateLoading || estimateError) { toast.error("Wait for a valid cost estimate before generating."); return; }
    setSubmitting(true);
    try {
      const [image_s3_key, audio_s3_key] = await Promise.all([
        upload(photo, "avatarPhoto"), upload(audio, "avatarAudio"),
      ]);
      setResult(await createAvatar({
        image_s3_key, audio_s3_key, model: estimate.model_id,
        duration_seconds: audioDuration ?? undefined,
      }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Generation failed to start.");
    } finally { setSubmitting(false); }
  }

  const busy = submitting || uploading || durationLoading || estimateLoading;

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <div className="mb-4"><h2 className="font-display text-lg font-semibold">Talking portrait</h2><p className="mt-1 text-sm text-muted-foreground">Use a clear speaker portrait and an audio track. We measure the audio duration where possible so the reservation is based on your clip, not a generic worst-case duration.</p></div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FileDropInput accept="image/*" label="Photo of the speaker" preview="image" onFile={setPhoto} />
          <FileDropInput accept="audio/*" label="Audio track to lip-sync" preview="audio" onFile={(file) => void chooseAudio(file)} />
        </div>
        <div className="mt-4 rounded-xl border border-border/80 bg-muted/35 p-3 text-xs leading-relaxed text-muted-foreground">Resolution is provider-native for this avatar model; Vivid Gen will not show a selectable resolution until the provider or our render pipeline can honor it.</div>
      </section>
      <GenerationEstimateCard estimate={estimate} loading={durationLoading || estimateLoading} error={estimateError} />
      <div className="flex flex-col-reverse gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">Checking a quote is free. Credits are reserved only after you start generation.</p><Button onClick={() => void onSubmit()} disabled={busy || !photo || !audio || !estimate || !!estimateError} className="h-11 rounded-xl bg-primary px-5 font-semibold text-primary-foreground hover:bg-primary/90">{uploading ? "Uploading files…" : submitting ? "Starting generation…" : durationLoading ? "Reading audio duration…" : estimateLoading ? "Updating estimate…" : estimate ? `Generate avatar · ${estimate.credits_to_reserve} credits` : "Generate avatar"}</Button></div>
      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}
