"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createProject } from "~/actions/projects";
import { createPlan } from "~/actions/director";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";

const PLATFORMS = [
  { value: "none", label: "No specific platform" },
  { value: "instagram_reels", label: "Instagram Reels" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube" },
  { value: "youtube_shorts", label: "YouTube Shorts" },
];

export function DirectorPromptForm({ initialPrompt = "" }: { initialPrompt?: string }) {
  const router = useRouter();
  const [prompt, setPrompt] = useState(initialPrompt);
  const [duration, setDuration] = useState(30);
  const [platform, setPlatform] = useState("none");
  const [style, setStyle] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!prompt.trim()) {
      toast.error("Describe what you want to create.");
      return;
    }
    setSubmitting(true);
    try {
      const project = await createProject({ title: prompt.slice(0, 80) });
      await createPlan(project.id, {
        prompt,
        duration_seconds: duration,
        target_platform: platform === "none" ? undefined : platform,
        style: style || undefined,
      });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The AI Director couldn't plan this one.");
      setSubmitting(false);
    }
  }

  return (
    <div className="neo-panel space-y-4 p-5">
      <Textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe an idea, e.g. a cinematic video of a city at sunset"
        rows={3}
        maxLength={5000}
        className="border-0 bg-transparent p-0 text-base shadow-none focus-visible:ring-0"
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <p className="text-muted-foreground mb-1 text-xs">Duration</p>
          <Select value={String(duration)} onValueChange={(v) => setDuration(Number(v))}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[15, 30, 45, 60, 90, 120].map((d) => (
                <SelectItem key={d} value={String(d)}>
                  {d}s
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-muted-foreground mb-1 text-xs">Platform</p>
          <Select value={platform} onValueChange={setPlatform}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLATFORMS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-muted-foreground mb-1 text-xs">Style (optional)</p>
          <Input value={style} onChange={(e) => setStyle(e.target.value)} placeholder="e.g. cinematic" />
        </div>
      </div>
      <div className="flex justify-end">
        <Button onClick={() => void onSubmit()} disabled={submitting} className="surface-gold">
          {submitting ? "Planning\u2026" : "Plan my video"}
        </Button>
      </div>
    </div>
  );
}
