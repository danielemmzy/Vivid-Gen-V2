"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createPresentationWorkflow } from "~/actions/workflows";
import { FileDropInput } from "~/components/file-drop-input";
import { Button } from "~/components/ui/button";
import { useDirectUpload } from "~/hooks/use-direct-upload";

export function PresentationForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a .pptx file first.");
      return;
    }
    setSubmitting(true);
    try {
      const pptx_s3_key = await upload(file, "presentationSource");
      const result = await createPresentationWorkflow({ pptx_s3_key });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't read or plan from that presentation.");
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <div className="space-y-4">
      <FileDropInput accept=".pptx" label="Drop a .pptx file, or click to browse" onFile={setFile} />
      <p className="text-muted-foreground text-xs">
        Slide text, embedded pictures, chart labels and speaker notes are extracted. Complex layouts are not yet rendered as full-slide screenshots, so review the storyboard before generating.
      </p>
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={busy}>
          {uploading ? "Uploading\u2026" : submitting ? "Reading slides\u2026" : "Plan my video"}
        </Button>
      </div>
    </div>
  );
}
