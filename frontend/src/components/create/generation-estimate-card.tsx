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
    <section className="border-border bg-card overflow-hidden rounded-2xl border shadow-[0_12px_36px_-28px_rgba(215,46,60,0.45)]">
      <div className="border-border/80 from-primary/[0.08] flex items-center justify-between border-b bg-gradient-to-r via-transparent to-transparent px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="bg-primary/10 text-primary flex size-8 items-center justify-center rounded-xl">
            <Calculator className="size-4" />
          </span>
          <div>
            <p className="text-sm font-semibold">Generation estimate</p>
            <p className="text-muted-foreground text-xs">
              Calculated by Vivid Gen
            </p>
          </div>
        </div>
        {loading ? (
          <span className="text-muted-foreground inline-flex items-center gap-2 text-xs">
            <span className="bg-primary size-2 animate-pulse rounded-full" />{" "}
            Updating quote
          </span>
        ) : estimate ? (
          <span className="border-primary/20 bg-primary/10 text-primary inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium">
            <BadgeCheck className="size-3.5" /> Ready
          </span>
        ) : null}
      </div>

      <div className="space-y-3 p-4">
        {error ? (
          <div className="border-destructive/25 bg-destructive/5 text-destructive rounded-xl border p-3 text-sm">
            {error}
          </div>
        ) : estimate ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-muted/65 rounded-xl p-3">
                <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs">
                  <Wallet className="size-3.5" /> Credits to reserve
                </div>
                <p className="font-display text-primary text-2xl font-semibold tracking-tight">
                  {estimate.credits_to_reserve.toLocaleString()}
                </p>
                <p className="text-muted-foreground mt-1 text-[11px]">
                  Estimated; final charge is reconciled after completion
                </p>
              </div>
              <div className="bg-muted/65 rounded-xl p-3">
                <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs">
                  <Cpu className="size-3.5" /> Provider cost estimate
                </div>
                <p className="font-display text-2xl font-semibold tracking-tight">
                  ${estimate.estimated_provider_cost_usd.toFixed(3)}
                </p>
                <p className="text-muted-foreground mt-1 text-[11px]">
                  Internal cost estimate, not a customer charge
                </p>
                {estimate.estimated_reservation_cost_usd >
                estimate.estimated_provider_cost_usd ? (
                  <p className="text-foreground mt-2 text-[11px] font-medium">
                    Reservation allowance: $
                    {estimate.estimated_reservation_cost_usd.toFixed(3)}
                  </p>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="border-border rounded-full border px-2.5 py-1 font-medium">
                {estimate.model_name}
              </span>
              <span className="border-border text-muted-foreground rounded-full border px-2.5 py-1">
                {estimate.provider === "modal"
                  ? "Self-hosted · Modal"
                  : estimate.provider}
              </span>
              {estimate.duration_seconds ? (
                <span className="border-border text-muted-foreground rounded-full border px-2.5 py-1">
                  {estimate.duration_seconds}s
                </span>
              ) : null}
              {estimate.resolution ? (
                <span className="border-border text-muted-foreground rounded-full border px-2.5 py-1">
                  {estimate.resolution}
                </span>
              ) : [
                  "text_to_video",
                  "image_to_video",
                  "avatar",
                  "video_translation",
                  "audio_replace",
                ].includes(estimate.generation_type) &&
                estimate.capabilities.resolution_mode ? (
                <span className="border-border text-muted-foreground rounded-full border px-2.5 py-1">
                  {estimate.capabilities.resolution_mode === "preserve_input"
                    ? "Preserves input resolution"
                    : "Provider-native resolution"}
                </span>
              ) : null}
            </div>
            <div className="border-border/80 text-muted-foreground flex gap-2 rounded-xl border p-3 text-xs leading-relaxed">
              <Info className="text-primary mt-0.5 size-4 shrink-0" />
              <span>{estimate.note ?? estimate.cost_estimate_basis}</span>
            </div>
          </>
        ) : (
          <div className="border-border text-muted-foreground rounded-xl border border-dashed p-4 text-sm">
            Enter your settings to calculate a quote before generation. No
            credits are spent by checking an estimate.
          </div>
        )}
      </div>
    </section>
  );
}
