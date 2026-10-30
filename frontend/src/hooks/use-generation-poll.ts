"use client";

import { useEffect, useRef, useState } from "react";
import { getGeneration, type GenerationResult } from "~/actions/generation";
import { isInFlight } from "~/components/generation-status-badge";

/**
 * Polls GET /generations/{id} (backend/app/routers/generations.py) while the
 * generation is in a non-terminal state, using the REAL backend states from
 * core/constants.py::GenerationStatus. Stops automatically once the backend
 * reports completed/failed/refunded — never invents a frontend-only
 * "done" state.
 */
export function useGenerationPoll(initial: GenerationResult, intervalMs = 4000) {
  const [generation, setGeneration] = useState(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setGeneration(initial);
  }, [initial.id]);

  useEffect(() => {
    if (!isInFlight(generation.status)) return;

    let cancelled = false;
    timer.current = setTimeout(async () => {
      try {
        const next = await getGeneration(generation.id);
        if (!cancelled) setGeneration(next);
      } catch {
        // Transient network/backend errors just get retried on the next tick.
      }
    }, intervalMs);

    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [generation, intervalMs]);

  return generation;
}
