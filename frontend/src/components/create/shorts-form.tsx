"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { createShortsWorkflow } from "~/actions/workflows";
import { FileDropInput } from "~/components/file-drop-input";
import { Button } from "~/components/ui/button";
import { useDirectUpload } from "~/hooks/use-direct-upload";

interface Clip {
  id: string;
  s3_key: string;
  duration_seconds: number;
  metadata: Record<string, unknown>;
}

export function ShortsForm() {
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const { upload, uploading } = useDirectUpload();

  async function onSubmit() {
    if (!file) {
      toast.error("Upload a video first.");
      return;
    }
    setSubmitting(true);
    try {
      const source_video_s3_key = await upload(file, "shortsSource");
      const result = await createShortsWorkflow({ source_video_s3_key });
      setProjectId(result.project_id);
      setClips(result.clips);
      if (result.clips.length === 0) {
        toast.error("No highlights were found in this video's transcript.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Couldn't process that video.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <div className="space-y-4">
      <FileDropInput
        accept="video/*"
        label="Drop a video, or click to browse"
        preview="video"
        onFile={setFile}
      />
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={busy}>
          {uploading
            ? "Uploading\u2026"
            : submitting
              ? "Finding highlights\u2026"
              : "Find Shorts"}
        </Button>
      </div>

      {projectId && clips.length > 0 && (
        <div className="space-y-2 rounded-lg border p-4">
          <p className="text-sm font-medium">
            {clips.length} clip{clips.length === 1 ? "" : "s"} found
          </p>
          {clips.map((clip) => (
            <div
              key={clip.id}
              className="flex items-center justify-between gap-3 rounded-lg border p-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm">
                  {typeof clip.metadata.reason === "string"
                    ? clip.metadata.reason
                    : "Highlight"}
                </p>
                <p className="text-muted-foreground font-data text-xs">
                  {clip.duration_seconds.toFixed(1)}s
                </p>
              </div>
            </div>
          ))}
          <Button asChild variant="outline" size="sm" className="mt-2">
            <Link href={`/projects/${projectId}`}>View project</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
