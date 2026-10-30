"use client";

import { formatDistanceToNow } from "date-fns/formatDistanceToNow";
import { Play, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { GenerationResult } from "~/actions/generation";
import { GenerationStatusBadge } from "~/components/generation-status-badge";
import { Input } from "~/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { isVideoType, TYPE_LABELS } from "~/lib/generation-types";

const STATUS_FILTERS = ["all", "processing", "completed", "failed"] as const;

export function GenerationsLibrary({ generations }: { generations: GenerationResult[] }) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const types = useMemo(() => Array.from(new Set(generations.map((g) => g.type))), [generations]);

  const filtered = generations.filter((g) => {
    if (typeFilter !== "all" && g.type !== typeFilter) return false;
    if (statusFilter === "processing" && !["queued", "reserving_credits", "processing", "postprocessing"].includes(g.status)) return false;
    if (statusFilter === "completed" && g.status !== "completed") return false;
    if (statusFilter === "failed" && !["failed", "refunded"].includes(g.status)) return false;
    if (query.trim()) {
      const haystack = `${g.title ?? ""} ${TYPE_LABELS[g.type] ?? g.type} ${g.model_id}`.toLowerCase();
      if (!haystack.includes(query.trim().toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title, type, or model\u2026"
            className="pl-9"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {types.map((t) => (
              <SelectItem key={t} value={t}>
                {TYPE_LABELS[t] ?? t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
          <SelectTrigger className="w-full sm:w-40">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <div className="text-muted-foreground rounded-xl border py-16 text-center text-sm">
          {generations.length === 0
            ? "Nothing here yet \u2014 start your first generation from Create."
            : "No generations match your filters."}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {filtered.map((g) => (
            <Link
              key={g.id}
              href={`/generations/${g.id}`}
              className="group border-border bg-card overflow-hidden rounded-lg border transition-colors hover:border-foreground/30"
            >
              <div className="bg-muted relative aspect-square overflow-hidden">
                {g.status === "completed" && g.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={g.thumbnail_url} alt="" className="size-full object-cover" />
                ) : g.status === "completed" && g.output_url && !isVideoType(g.type) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={g.output_url} alt="" className="size-full object-cover" />
                ) : (
                  <div className="flex size-full items-center justify-center">
                    <GenerationStatusBadge status={g.status} />
                  </div>
                )}
                {g.status === "completed" && isVideoType(g.type) && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/20">
                    <Play className="size-8 text-white opacity-0 drop-shadow transition-opacity group-hover:opacity-100" />
                  </div>
                )}
              </div>
              <div className="space-y-1 p-2.5">
                <p className="truncate text-sm font-medium">{g.title ?? TYPE_LABELS[g.type] ?? g.type}</p>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground text-xs">{TYPE_LABELS[g.type] ?? g.type}</span>
                  {g.created_at && (
                    <span className="text-muted-foreground text-xs">
                      {formatDistanceToNow(new Date(g.created_at), { addSuffix: true })}
                    </span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
