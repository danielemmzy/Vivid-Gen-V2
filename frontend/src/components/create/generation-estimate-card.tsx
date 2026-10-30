"use client";

import { BadgeCheck, Calculator, Cpu, Info, Wallet } from "lucide-react";
import type { GenerationEstimate } from "~/actions/generation";

export function GenerationEstimateCard({
  estimate,
  loading,
  error,
}: {
  estimate: GenerationEstimate | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_12px_36px_-28px_rgba(215,46,60,0.45)]">
      <div className="flex items-center justify-between border-b border-border/80 bg-gradient-to-r from-primary/[0.08] via-transparent to-transparent px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Calculator className="size-4" />
          </span>
          <div>
            <p className="text-sm font-semibold">Generation estimate</p>
            <p className="text-xs text-muted-foreground">Calculated by Vivid Gen</p>
          </div>
        </div>
        {loading ? (
          <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
            <span className="size-2 animate-pulse rounded-full bg-primary" /> Updating quote
          </span>
        ) : estimate ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
            <BadgeCheck className="size-3.5" /> Ready
          </span>
        ) : null}
      </div>

      <div className="space-y-3 p-4">
        {error ? (
          <div className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>
        ) : estimate ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-muted/65 p-3">
                <div className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Wallet className="size-3.5" /> Credits to reserve
                </div>
                <p className="font-display text-2xl font-semibold tracking-tight text-primary">
                  {estimate.credits_to_reserve.toLocaleString()}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">Estimated; final charge is reconciled after completion</p>
              </div>
              <div className="rounded-xl bg-muted/65 p-3">
                <div className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Cpu className="size-3.5" /> Provider cost estimate
                </div>
                <p className="font-display text-2xl font-semibold tracking-tight">
                  ${estimate.estimated_provider_cost_usd.toFixed(3)}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">Internal cost estimate, not a customer charge</p>
                {estimate.estimated_reservation_cost_usd > estimate.estimated_provider_cost_usd ? <p className="mt-2 text-[11px] font-medium text-foreground">Reservation allowance: ${estimate.estimated_reservation_cost_usd.toFixed(3)}</p> : null}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-full border border-border px-2.5 py-1 font-medium">{estimate.model_name}</span>
              <span className="rounded-full border border-border px-2.5 py-1 text-muted-foreground">{estimate.provider === "modal" ? "Self-hosted · Modal" : estimate.provider}</span>
              {estimate.duration_seconds ? <span className="rounded-full border border-border px-2.5 py-1 text-muted-foreground">{estimate.duration_seconds}s</span> : null}
              {estimate.resolution ? <span className="rounded-full border border-border px-2.5 py-1 text-muted-foreground">{estimate.resolution}</span> : ["text_to_video", "image_to_video", "avatar", "video_translation", "audio_replace"].includes(estimate.generation_type) && estimate.capabilities.resolution_mode ? <span className="rounded-full border border-border px-2.5 py-1 text-muted-foreground">{estimate.capabilities.resolution_mode === "preserve_input" ? "Preserves input resolution" : "Provider-native resolution"}</span> : null}
            </div>
            <div className="flex gap-2 rounded-xl border border-border/80 p-3 text-xs leading-relaxed text-muted-foreground">
              <Info className="mt-0.5 size-4 shrink-0 text-primary" />
              <span>{estimate.note || estimate.cost_estimate_basis}</span>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
            Enter your settings to calculate a quote before generation. No credits are spent by checking an estimate.
          </div>
        )}
      </div>
    </section>
  );
}
