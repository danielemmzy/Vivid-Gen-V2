import type { CatalogModel } from "~/actions/models";

/**
 * Conservative display-only estimate based on the backend's per-unit credit
 * quote. Video models now return a true per-output-second unit (Modal's unit
 * price is derived from measured runtime and resource rates), not a five-
 * second sample. The authoritative quote is POST /models/estimate.
 */
export function estimateCredits(model: CatalogModel, durationSeconds?: number): number {
  if (model.unit === "image" || model.unit === "flat") return model.credits_per_unit;
  if (model.unit === "second") return Math.ceil(model.credits_per_unit * (durationSeconds ?? 5));
  if (model.unit === "minute") {
    return durationSeconds == null
      ? model.credits_per_unit
      : Math.ceil(model.credits_per_unit * (durationSeconds / 60));
  }
  return model.credits_per_unit;
}
