"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createPodcastWorkflow } from "~/actions/workflows";
import { FileDropInput } from "~/components/file-drop-input";
import { Button } from "~/components/ui/button";
import { useDirectUpload } from "~/hooks/use-direct-upload";

export function PodcastForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload an audio file first.");
      return;
    }
    setSubmitting(true);
    try {
      const audio_s3_key = await upload(file, "podcastSource");
      const result = await createPodcastWorkflow({ audio_s3_key });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't transcribe or plan from that audio.");
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <div className="space-y-4">
      <FileDropInput accept="audio/*" label="Drop an audio file, or click to browse" preview="audio" onFile={setFile} />
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={busy}>
          {uploading ? "Uploading\u2026" : submitting ? "Transcribing\u2026" : "Plan my video"}
        </Button>
      </div>
    </div>
  );
}
