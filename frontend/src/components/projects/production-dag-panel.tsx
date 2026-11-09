"use client";

import { useEffect, useState } from "react";
import { getProductionDag } from "~/actions/productions";
import type {
  ProductionTaskEdge,
  ProductionTaskResult,
} from "~/actions/productions";
import { cn } from "~/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  blocked: "text-muted-foreground",
  ready: "text-foreground",
  running: "text-warning",
  completed: "text-success",
  failed: "text-destructive",
  skipped: "text-muted-foreground",
};

const STATUS_ORDER = [
  "failed",
  "running",
  "ready",
  "blocked",
  "completed",
  "skipped",
];

function taskLabel(task: ProductionTaskResult): string {
  if (task.type === "scene") return `Scene ${task.scene_number}`;
  return task.type.charAt(0).toUpperCase() + task.type.slice(1);
}

/**
 * gap-closure (0007): a real dependency graph now backs this (see
 * backend/app/orchestration/dag.py, orchestration/scheduler.py) —
 * previously (round 2) this component's own docstring said the backend
 * was "explicitly NOT a dependency-DAG" and every task was shown
 * independently with no edges at all. This renders the actual graph:
 * each task's upstream dependencies are listed under it, so "why is
 * Render still blocked" is answerable by reading the panel, not by
 * guessing.
 *
 * Deliberately a grouped list, not a node-and-line canvas diagram — a
 * real graph renderer is a larger, separate UI investment; this gives
 * the same information (status per task, real dependency edges) without
 * introducing a new charting/graph-layout library for one panel.
 */
export function ProductionDagPanel({
  productionId,
  active,
}: {
  productionId: string;
  active: boolean;
}) {
  const [tasks, setTasks] = useState<ProductionTaskResult[]>([]);
  const [edges, setEdges] = useState<ProductionTaskEdge[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const result = await getProductionDag(productionId);
        if (!cancelled) {
          setTasks(result.tasks);
          setEdges(result.edges);
        }
      } catch {
        // best-effort; try again next tick
      } finally {
        if (!cancelled) setLoaded(true);
      }
      if (!cancelled && active) {
        timer = setTimeout(() => {
          void poll();
        }, 4000);
      }
    }
    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [productionId, active]);

  if (!loaded || tasks.length === 0) return null;

  const taskById = new Map(tasks.map((t) => [t.id, t]));
  const upstreamOf = new Map<string, string[]>();
  for (const edge of edges) {
    const list = upstreamOf.get(edge.downstream_task_id) ?? [];
    list.push(edge.upstream_task_id);
    upstreamOf.set(edge.downstream_task_id, list);
  }

  const sorted = [...tasks].sort((a, b) => {
    const rank = (t: ProductionTaskResult) => STATUS_ORDER.indexOf(t.status);
    const byStatus = rank(a) - rank(b);
    if (byStatus !== 0) return byStatus;
    return (a.scene_number ?? 0) - (b.scene_number ?? 0);
  });

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium">Production DAG</h2>
      <div className="space-y-1.5">
        {sorted.map((task) => {
          const upstream = (upstreamOf.get(task.id) ?? [])
            .map((id) => taskById.get(id))
            .filter((t): t is ProductionTaskResult => Boolean(t));
          return (
            <div
              key={task.id}
              className="flex items-baseline justify-between gap-3 rounded-lg border px-3 py-1.5 text-xs"
            >
              <div className="min-w-0">
                <span
                  className={cn(
                    "font-medium",
                    STATUS_CLASS[task.status] ?? "text-muted-foreground",
                  )}
                >
                  {taskLabel(task)}
                </span>
                {upstream.length > 0 && (
                  <span className="text-muted-foreground ml-2">
                    after {upstream.map(taskLabel).join(", ")}
                  </span>
                )}
                {task.error && (
                  <span className="text-destructive ml-2">{task.error}</span>
                )}
              </div>
              <span
                className={cn(
                  "shrink-0 capitalize",
                  STATUS_CLASS[task.status] ?? "text-muted-foreground",
                )}
              >
                {task.status}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
