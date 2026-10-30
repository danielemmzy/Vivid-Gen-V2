"use client";

import Link from "next/link";
import type { GenerationResult } from "~/actions/generation";
import { GenerationStatusBadge } from "~/components/generation-status-badge";
import { Button } from "~/components/ui/button";
import { useGenerationPoll } from "~/hooks/use-generation-poll";
import { isVideoType } from "~/lib/generation-types";

export function GenerationResultPanel({ initial }: { initial: GenerationResult }) {
  const generation = useGenerationPoll(initial);

  return (
    <div className="space-y-3 rounded-xl border p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Your generation</p>
        <GenerationStatusBadge status={generation.status} />
      </div>
      {generation.status === "completed" && generation.output_url ? (
        <div className="bg-muted overflow-hidden rounded-lg">
          {isVideoType(generation.type) ? (
            <video src={generation.output_url} controls className="max-h-80 w-full" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={generation.output_url} alt="" className="max-h-80 w-full object-contain" />
          )}
        </div>
      ) : generation.status === "failed" ? (
        <p className="text-destructive text-sm">{generation.error_message ?? "This generation failed."}</p>
      ) : (
        <p className="text-muted-foreground text-xs">This updates automatically as it processes.</p>
      )}
      <Button asChild variant="outline" size="sm">
        <Link href={`/generations/${generation.id}`}>View details</Link>
      </Button>
    </div>
  );
}
