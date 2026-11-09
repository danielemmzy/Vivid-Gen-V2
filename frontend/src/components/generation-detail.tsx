"use client";

import { format } from "date-fns/format";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import type { GenerationResult } from "~/actions/generation";
import { cancelGeneration } from "~/actions/generation";
import { updateCreationName } from "~/actions/creations";
import {
  GenerationStatusBadge,
  isInFlight,
} from "~/components/generation-status-badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { useGenerationPoll } from "~/hooks/use-generation-poll";
import { isVideoType, TYPE_LABELS } from "~/lib/generation-types";

// gap-closure: matches backend/app/core/constants.py::GenerationStatus —
// only these states are actually cancellable server-side (see
// GenerationService.cancel); showing the button in other states would
// just produce a 400 GENERATION_NOT_CANCELLABLE.
const CANCELLABLE_STATUSES = new Set([
  "queued",
  "reserving_credits",
  "processing",
  "postprocessing",
]);

export function GenerationDetail({ initial }: { initial: GenerationResult }) {
  const generation = useGenerationPoll(initial);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(generation.title ?? "");
  const [saving, setSaving] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateCreationName(
        generation.id,
        title ?? TYPE_LABELS[generation.type] ?? generation.type,
      );
      setEditing(false);
    } catch {
      toast.error("Couldn't rename that generation.");
    } finally {
      setSaving(false);
    }
  }

  async function cancel() {
    setCancelling(true);
    try {
      await cancelGeneration(generation.id);
      toast.success(
        "Generation cancelled — any unspent credits were refunded.",
      );
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Couldn't cancel that generation.",
      );
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex items-center gap-2">
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && void save()}
                className="font-display max-w-sm text-xl"
              />
              <Button size="sm" onClick={() => void save()} disabled={saving}>
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="group flex items-center gap-2 text-left"
            >
              <h1 className="font-display truncate text-2xl font-semibold">
                {generation.title ??
                  TYPE_LABELS[generation.type] ??
                  generation.type}
              </h1>
              <Pencil className="text-muted-foreground size-4 opacity-0 group-hover:opacity-100" />
            </button>
          )}
        </div>
        <GenerationStatusBadge
          status={generation.status}
          className="shrink-0"
        />
        {CANCELLABLE_STATUSES.has(generation.status) && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void cancel()}
            disabled={cancelling}
            className="shrink-0"
          >
            {cancelling ? "Cancelling\u2026" : "Cancel"}
          </Button>
        )}
      </div>

      <div className="bg-muted overflow-hidden rounded-xl border">
        {generation.status === "completed" && generation.output_url ? (
          isVideoType(generation.type) ? (
            <video
              src={generation.output_url}
              controls
              className="max-h-[60vh] w-full"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={generation.output_url}
              alt=""
              className="max-h-[60vh] w-full object-contain"
            />
          )
        ) : generation.status === "failed" ? (
          <div className="flex flex-col items-center gap-2 py-20 text-center">
            <p className="text-destructive text-sm font-medium">
              {generation.error_message ?? "This generation failed."}
            </p>
            {generation.error_code && (
              <p className="text-muted-foreground font-data text-xs">
                {generation.error_code}
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-20 text-center">
            <GenerationStatusBadge status={generation.status} />
            {isInFlight(generation.status) && (
              <p className="text-muted-foreground text-xs">
                This updates automatically \u2014 no need to refresh.
              </p>
            )}
          </div>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        <Field
          label="Type"
          value={TYPE_LABELS[generation.type] ?? generation.type}
        />
        <Field label="Model" value={generation.model_id} mono />
        {generation.duration_seconds != null && (
          <Field
            label="Duration"
            value={`${generation.duration_seconds}s`}
            mono
          />
        )}
        {generation.resolution && (
          <Field label="Output resolution" value={generation.resolution} mono />
        )}
        {generation.aspect_ratio && (
          <Field label="Aspect ratio" value={generation.aspect_ratio} mono />
        )}
        <Field
          label="Created"
          value={
            generation.created_at
              ? format(
                  new Date(generation.created_at),
                  "MMM d, yyyy \u00b7 h:mm a",
                )
              : "\u2014"
          }
        />
        <Field
          label="Credits reserved"
          value={generation.credits_reserved.toLocaleString()}
          mono
        />
        <Field
          label="Credits charged"
          value={generation.credits_charged.toLocaleString()}
          mono
        />
        <Field
          label="Est. provider cost"
          value={`$${generation.estimated_provider_cost_usd.toFixed(4)}`}
          mono
        />
        {generation.actual_provider_cost_usd != null && (
          <Field
            label={
              generation.actual_cost_source === "provider_reported"
                ? "Provider-reported cost"
                : generation.actual_cost_source === "modal_runtime_estimate"
                  ? "Modal runtime cost estimate"
                  : "Provider cost estimate"
            }
            value={`$${generation.actual_provider_cost_usd.toFixed(4)} · ${generation.actual_cost_source === "modal_runtime_estimate" ? "estimated; not invoice-reconciled" : generation.actual_cost_source === "catalog_estimate" ? "catalog rates; estimated" : generation.actual_cost_source === "provider_reported" ? "reported by provider" : (generation.actual_cost_source ?? "source unavailable")}`}
            mono
          />
        )}
        {generation.retry_count > 0 && (
          <Field
            label="Retries"
            value={`${generation.retry_count} (automatic fallback)`}
            mono
          />
        )}
      </dl>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className={mono ? "font-data text-sm" : "text-sm"}>{value}</dd>
    </div>
  );
}
