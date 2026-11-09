"use client";

import { useEffect, useState } from "react";
import {
  estimateGeneration,
  type GenerationEstimate,
  type GenerationEstimateRequest,
} from "~/actions/generation";

/** Debounced, server-authoritative quote. It never reserves or spends credits. */
export function useGenerationEstimate(
  request: GenerationEstimateRequest | null,
  delayMs = 250,
) {
  const requestKey = request ? JSON.stringify(request) : "";
  const [estimate, setEstimate] = useState<GenerationEstimate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!requestKey) {
      setEstimate(null);
      setLoading(false);
      setError(null);
      return () => {
        active = false;
      };
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true);
        setError(null);
        try {
          const quote = await estimateGeneration(
            JSON.parse(requestKey) as GenerationEstimateRequest,
          );
          if (active) setEstimate(quote);
        } catch (cause) {
          if (active) {
            setEstimate(null);
            setError(
              cause instanceof Error
                ? cause.message
                : "Unable to calculate this estimate.",
            );
          }
        } finally {
          if (active) setLoading(false);
        }
      })();
    }, delayMs);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [requestKey, delayMs]);

  return { estimate, loading, error };
}
