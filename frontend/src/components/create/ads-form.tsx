"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createAdWorkflow } from "~/actions/workflows";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { cn } from "~/lib/utils";

const PLATFORMS = ["instagram_reels", "tiktok", "youtube_shorts"];
const DURATIONS = [15, 30, 45, 60, 90];

export function AdsForm() {
  const router = useRouter();
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [audience, setAudience] = useState("");
  const [goal, setGoal] = useState("");
  const [platform, setPlatform] = useState("instagram_reels");
  const [duration, setDuration] = useState(30);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!productName.trim() || !description.trim()) {
      toast.error("Product name and description are required \u2014 the Director only uses real facts you give it.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createAdWorkflow({
        product_name: productName, product_description: description,
        audience: audience || undefined, goal: goal || undefined,
        platform, duration_seconds: duration,
      });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't plan this ad.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Input value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="Product name" maxLength={200} />
      <Textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describe the product \u2014 real facts only, this is what the Director bases the ad on"
        rows={3}
        maxLength={3000}
      />
      <Input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Audience (optional), e.g. \u201cmen 18-30\u201d" maxLength={200} />
      <Input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Goal (optional), e.g. \u201cdrive purchases\u201d" maxLength={200} />

      <div>
        <p className="mb-2 text-xs font-medium">Platform</p>
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={cn(
                "rounded-md border px-3 py-1.5 text-sm transition-colors",
                platform === p ? "border-foreground bg-foreground text-background" : "border-border hover:border-foreground/40",
              )}
            >
              {p.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs font-medium">Duration</p>
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
              {d}s
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={submitting}>
          {submitting ? "Planning\u2026" : "Plan my ad"}
        </Button>
      </div>
    </div>
  );
}
