"use client";

import { useState } from "react";
import { toast } from "sonner";
import { changeVideoAudio, type GenerationResult } from "~/actions/generation";
import { GenerationEstimateCard } from "~/components/create/generation-estimate-card";
import { useGenerationEstimate } from "~/hooks/use-generation-estimate";
import { readMediaDuration } from "~/hooks/use-media-duration";
import { FileDropInput } from "~/components/file-drop-input";
import { GenerationResultPanel } from "~/components/generation-result-panel";
import { Button } from "~/components/ui/button";
import { useDirectUpload } from "~/hooks/use-direct-upload";

export function AudioReplaceForm() {
  const [video, setVideo] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [sourceDuration, setSourceDuration] = useState<number | null>(null);
  const [durationLoading, setDurationLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const { upload, uploading } = useDirectUpload();
  const { estimate, loading: estimateLoading, error: estimateError } = useGenerationEstimate(video && !durationLoading ? {
    generation_type: "audio_replace", model_id: "audio-replace", duration_seconds: sourceDuration ?? undefined,
  } : null);

  async function chooseVideo(file: File | null) {
    setVideo(file);
    setSourceDuration(null);
    if (!file) return;
    setDurationLoading(true);
    try { setSourceDuration(await readMediaDuration(file)); }
    finally { setDurationLoading(false); }
  }

  async function onSubmit() {
    if (!video || !audio) {
      toast.error("A source video and a replacement audio track are both required.");
      return;
    }
    if (!estimate || estimateError) { toast.error("Wait for a valid cost estimate before generating."); return; }
    setSubmitting(true);
    try {
      const [sourceVideoS3Key, newAudioS3Key] = await Promise.all([
        upload(video, "audioReplaceVideo"),
        upload(audio, "audioReplaceAudio"),
      ]);
      const generation = await changeVideoAudio({
        sourceVideoS3Key,
        newAudioS3Key,
        videoName: video.name,
        sourceDurationSeconds: sourceDuration ?? undefined,
        model: estimate.model_id,
      });
      setResult(generation);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed to start.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading || durationLoading || estimateLoading;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FileDropInput accept="video/*" label="Source video" preview="video" onFile={(file) => void chooseVideo(file)} />
        <FileDropInput accept="audio/*" label="Replacement audio" preview="audio" onFile={setAudio} />
      </div>

      <GenerationEstimateCard estimate={estimate} loading={durationLoading || estimateLoading} error={estimateError} />
      <div className="flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">The quote uses source video duration when available. Credits are reserved only when you start.</p><Button onClick={() => void onSubmit()} disabled={busy || !video || !audio || !estimate || !!estimateError} className="rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">{uploading ? "Uploading files…" : submitting ? "Processing…" : estimateLoading ? "Updating estimate…" : estimate ? `Replace audio · ${estimate.credits_to_reserve} credits` : "Replace audio"}</Button></div>

      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}
