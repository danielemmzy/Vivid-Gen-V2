"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createYoutubeWorkflow } from "~/actions/workflows";
import { Button } from "~/components/ui/button";
import { Textarea } from "~/components/ui/textarea";
import { cn } from "~/lib/utils";

const DURATIONS = [60, 120, 180, 300, 420, 600];

export function YoutubeForm() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState(180);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!topic.trim()) {
      toast.error("Describe the topic first.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createYoutubeWorkflow({ topic, duration_seconds: duration });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't plan this video.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Textarea
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder="e.g. \u201cHow Bitcoin mining actually works\u201d"
        rows={3}
        maxLength={500}
      />
      <p className="text-muted-foreground text-xs">
        Note: the Director isn&apos;t grounded in real research for this workflow yet \u2014 it plans from its own
        general knowledge, same as asking any AI a factual question. For a fact-checked video, use From URL instead.
      </p>
      <div>
        <p className="mb-2 text-xs font-medium">Target duration</p>
        <div className="flex flex-wrap gap-2">
          {DURATIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDuration(d)}
              className={cn(
                "rounded-md border px-3 py-1.5 text-sm transition-colors",
                duration === d ? "border-foreground bg-foreground text-background" : "border-border hover:border-foreground/40",
              )}
            >
              {d < 60 ? `${d}s` : `${Math.round(d / 60)}m`}
            </button>
          ))}
        </div>
      </div>
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={submitting}>
          {submitting ? "Planning\u2026" : "Plan my video"}
        </Button>
      </div>
    </div>
  );
}
