"use client";

import { useState } from "react";
import { toast } from "sonner";
import { translateVideo, type GenerationResult } from "~/actions/generation";
import { GenerationEstimateCard } from "~/components/create/generation-estimate-card";
import { useGenerationEstimate } from "~/hooks/use-generation-estimate";
import { readMediaDuration } from "~/hooks/use-media-duration";
import { FileDropInput } from "~/components/file-drop-input";
import { GenerationResultPanel } from "~/components/generation-result-panel";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Switch } from "~/components/ui/switch";
import { useDirectUpload } from "~/hooks/use-direct-upload";

// The backend's VideoTranslationRequest.target_language just accepts any
// 2-10 char string (see schemas/generation.py) \u2014 there's no backend-defined
// language list. This is a frontend convenience list of common targets, not
// a verified backend enum, so a code typed elsewhere would work too.
const LANGUAGES = [
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "pt", label: "Portuguese" },
  { code: "hi", label: "Hindi" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "zh", label: "Chinese (Mandarin)" },
  { code: "ar", label: "Arabic" },
];

export function TranslateForm() {
  const [file, setFile] = useState<File | null>(null);
  const [targetLanguage, setTargetLanguage] = useState("es");
  const [lipSync, setLipSync] = useState(true);
  const [sourceDuration, setSourceDuration] = useState<number | null>(null);
  const [durationLoading, setDurationLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const { estimate, loading: estimateLoading, error: estimateError } = useGenerationEstimate(file && !durationLoading ? {
    generation_type: "video_translation",
    model_id: lipSync ? "video-translate-dub" : "video-dub-audio-only",
    duration_seconds: sourceDuration ?? undefined,
  } : null);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a source video first.");
      return;
    }
    setSubmitting(true);
    try {
      if (!estimate || estimateError) { toast.error("Wait for a valid cost estimate before generating."); return; }
      const sourceVideoS3Key = await upload(file, "videoTranslationSource");
      const generation = await translateVideo({ sourceVideoS3Key, targetLanguage, lipSync, model: estimate.model_id, sourceDurationSeconds: sourceDuration ?? undefined });
      setResult(generation);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed to start.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading || durationLoading || estimateLoading;
  async function chooseVideo(file: File | null) {
    setFile(file);
    setSourceDuration(null);
    if (!file) return;
    setDurationLoading(true);
    try { setSourceDuration(await readMediaDuration(file)); }
    finally { setDurationLoading(false); }
  }

  return (
    <div className="space-y-5">
      <FileDropInput accept="video/*" label="Drop a video, or click to browse" preview="video" onFile={(file) => void chooseVideo(file)} />

      <div>
        <p className="mb-2 text-xs font-medium">Target language</p>
        <Select value={targetLanguage} onValueChange={setTargetLanguage}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((l) => (
              <SelectItem key={l.code} value={l.code}>
                {l.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <label className="flex items-center justify-between rounded-lg border p-3">
        <div>
          <p className="text-sm font-medium">Lip-sync</p>
          <p className="text-muted-foreground text-xs">Match mouth movement to the translated audio.</p>
        </div>
        <Switch checked={lipSync} onCheckedChange={setLipSync} />
      </label>

      <GenerationEstimateCard estimate={estimate} loading={durationLoading || estimateLoading} error={estimateError} />
      <div className="flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-muted-foreground">The source duration determines the reservation when browser metadata is available.</p><Button onClick={() => void onSubmit()} disabled={busy || !file || !estimate || !!estimateError} className="rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">{uploading ? "Uploading…" : submitting ? "Translating…" : estimateLoading ? "Updating estimate…" : estimate ? `Translate · ${estimate.credits_to_reserve} credits` : "Translate video"}</Button></div>

      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}
