"use client";

import { useState } from "react";
import { toast } from "sonner";
import { createDubbingWorkflow } from "~/actions/workflows";
import type { GenerationResult } from "~/actions/generation";
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

export function DubbingForm() {
  const [file, setFile] = useState<File | null>(null);
  const [targetLanguage, setTargetLanguage] = useState("es");
  const [lipSync, setLipSync] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a video first.");
      return;
    }
    setSubmitting(true);
    try {
      const source_video_s3_key = await upload(file, "dubbingSource");
      const generation = await createDubbingWorkflow({ source_video_s3_key, target_language: targetLanguage, lip_sync: lipSync });
      setResult(generation);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't start dubbing.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <div className="space-y-4">
      <FileDropInput accept="video/*" label="Drop a video, or click to browse" preview="video" onFile={setFile} />
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
      <label className="flex items-center justify-between rounded-lg border p-3">
        <p className="text-sm font-medium">Lip-sync</p>
        <Switch checked={lipSync} onCheckedChange={setLipSync} />
      </label>
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={busy}>
          {uploading ? "Uploading\u2026" : submitting ? "Starting\u2026" : "Dub video"}
        </Button>
      </div>
      {result && <GenerationResultPanel initial={result} />}
    </div>
  );
}
