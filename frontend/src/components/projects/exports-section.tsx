"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { createExport, listExports } from "~/actions/exports";
import type {
  ExportAspectRatio,
  ExportPlatform,
  ExportResult,
} from "~/actions/exports";
import { Button } from "~/components/ui/button";
import { cn } from "~/lib/utils";

const PRESETS: {
  platform: ExportPlatform;
  aspectRatio: ExportAspectRatio;
  label: string;
}[] = [
  { platform: "youtube", aspectRatio: "16:9", label: "YouTube (16:9)" },
  { platform: "tiktok", aspectRatio: "9:16", label: "TikTok / Shorts (9:16)" },
  {
    platform: "instagram_feed",
    aspectRatio: "1:1",
    label: "Instagram feed (1:1)",
  },
  {
    platform: "instagram_reels",
    aspectRatio: "4:5",
    label: "Instagram feed (4:5)",
  },
];

/**
 * gap-closure: Content Factory MVP. Before this, "export" meant nothing
 * more than the master video's own presigned URL — this lets a user
 * generate real, listable, re-downloadable aspect-ratio variants. See
 * backend/app/services/export/service.py for exactly what this does and
 * does not do (no auto-generated per-platform titles/thumbnails — a
 * mechanical reframe + a real Export record, nothing more).
 *
 * Fetches its own list client-side on mount rather than requiring the
 * server page to fetch and prop-drill it — this section only renders once
 * a project is `ready`, so there's no risk of it firing before a master
 * exists.
 */
export function ExportsSection({ projectId }: { projectId: string }) {
  const [exports, setExports] = useState<ExportResult[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listExports(projectId)
      .then(({ exports: next }) => {
        if (!cancelled) setExports(next);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function onCreate(preset: (typeof PRESETS)[number]) {
    setCreating(preset.label);
    try {
      const result = await createExport(
        projectId,
        preset.platform,
        preset.aspectRatio,
      );
      setExports((prev) => [result, ...prev.filter((e) => e.id !== result.id)]);
      if (result.status === "completed") {
        toast.success(`${preset.label} export ready.`);
      } else if (result.status === "failed") {
        toast.error(
          `${preset.label} export failed: ${result.error ?? "unknown error"}`,
        );
      }
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : `Couldn't create the ${preset.label} export.`,
      );
    } finally {
      setCreating(null);
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium">Exports</h2>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((preset) => (
          <Button
            key={preset.label}
            size="sm"
            variant="outline"
            disabled={creating !== null}
            onClick={() => void onCreate(preset)}
          >
            {creating === preset.label
              ? "Rendering\u2026"
              : `Export for ${preset.label}`}
          </Button>
        ))}
      </div>
      {loaded && exports.length > 0 && (
        <div className="space-y-2">
          {exports.map((exp) => (
            <div
              key={exp.id}
              className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"
            >
              <div className="min-w-0">
                <p className="truncate">
                  {exp.platform} &middot; {exp.aspect_ratio}
                </p>
                {exp.status === "failed" && (
                  <p className="text-destructive text-xs">{exp.error}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={cn(
                    "text-xs",
                    exp.status === "completed" && "text-success",
                    exp.status === "failed" && "text-destructive",
                    exp.status === "processing" && "text-warning",
                  )}
                >
                  {exp.status}
                </span>
                {exp.status === "completed" && exp.download_url && (
                  <a
                    href={exp.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs underline underline-offset-2"
                  >
                    Download
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
