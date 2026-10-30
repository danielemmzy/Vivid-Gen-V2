"use client";

import { useEffect, useState } from "react";
import { getProductionBudget } from "~/actions/productions";
import type { ProductionBudgetResult } from "~/actions/productions";

/**
 * gap-closure (0007): ProductionBudget — previously a production's
 * cost lifecycle (estimate/reserve/consume/refund) was implicit across
 * scattered Generation fields with no production-level rollup and no
 * frontend surface at all. See backend/app/models/production_budget.py.
 */
export function ProductionBudgetPanel({ productionId }: { productionId: string }) {
  const [budget, setBudget] = useState<ProductionBudgetResult | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProductionBudget(productionId)
      .then((result) => {
        if (!cancelled) setBudget(result.budget);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [productionId]);

  if (!loaded || !budget) return null;

  return (
    <section className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">Production budget</h2>
          <p className="text-muted-foreground mt-0.5 text-xs">
            {budget.budget_profile === "long_form" ? "Long-form movie" : "Short-form video"} · up to {budget.max_shots} shots · {budget.max_retries_per_shot} {budget.max_retries_per_shot === 1 ? "retry" : "retries"} per shot
          </p>
        </div>
        <span className="bg-muted rounded-full px-2.5 py-1 text-[11px] font-medium capitalize">{budget.status}</span>
      </div>
      <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Estimated</dt>
          <dd className="font-data">{budget.estimated_credits}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Reserved</dt>
          <dd className="font-data">{budget.reserved_credits}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Consumed</dt>
          <dd className="font-data">{budget.consumed_credits}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Refunded</dt>
          <dd className="font-data">{budget.refunded_credits}</dd>
        </div>
      </dl>
    </section>
  );
}
