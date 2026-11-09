"use client";

import { useEffect, useRef, useState } from "react";
import { getProject } from "~/actions/projects";
import type { Character, Project, Shot } from "~/actions/projects";
import { isProjectInFlight } from "~/components/projects/status-badges";

type FullProject = Project & { shots: Shot[]; characters: Character[] };

/**
 * gap-closure: production-progress.tsx has said "This updates
 * automatically — no need to refresh" since it was written, but nothing
 * backed that claim — the Project detail page is a server component that
 * fetches once per load, with no polling/SSE/WebSocket anywhere. This
 * hook is what makes that text true: polls GET /projects/{id}
 * (backend/app/routers/projects.py) every `intervalMs` while the project
 * is in a non-terminal state, mirroring hooks/use-generation-poll.ts's
 * same pattern for a single generation.
 */
export function useProjectPoll(initial: FullProject, intervalMs = 4000) {
  const [project, setProject] = useState(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setProject(initial);
  }, [initial.id, initial.status]);

  useEffect(() => {
    const anyShotInFlight = project.shots.some(
      (s) =>
        s.status === "pending" ||
        s.status === "queued" ||
        s.status === "processing",
    );
    if (!isProjectInFlight(project.status) && !anyShotInFlight) return;

    let cancelled = false;
    timer.current = setTimeout(() => {
      void (async () => {
        try {
          const next = await getProject(project.id);
          if (!cancelled) setProject(next);
        } catch {
          // Transient network/backend errors just get retried on the next tick.
        }
      })();
    }, intervalMs);

    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [project, intervalMs]);

  return project;
}
