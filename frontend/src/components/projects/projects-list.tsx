"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { createProject, type Project } from "~/actions/projects";
import { ProjectStatusBadge } from "~/components/projects/status-badges";
import { Button } from "~/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";

export function ProjectsList({ projects }: { projects: Project[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const filteredProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return projects.filter((project) => {
      if (status !== "all" && project.status !== status) return false;
      if (!normalizedQuery) return true;
      return `${project.title} ${project.description ?? ""}`
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [projects, query, status]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {projects.length > 0 && (
          <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row">
            <div className="relative min-w-0 flex-1">
              <Search
                aria-hidden="true"
                className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2"
              />
              <Input
                aria-label="Search projects"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search projects…"
                className="pl-9"
              />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger
                aria-label="Filter projects by status"
                className="w-full sm:w-44"
              >
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="planning">Planning</SelectItem>
                <SelectItem value="awaiting_approval">Needs review</SelectItem>
                <SelectItem value="generating">Generating</SelectItem>
                <SelectItem value="assembling">Assembling</SelectItem>
                <SelectItem value="ready">Ready</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}
        <NewProjectDialog />
      </div>

      {projects.length === 0 ? (
        <div className="text-muted-foreground rounded-xl border py-16 text-center text-sm">
          No projects yet \u2014 start one to build a multi-shot video with
          consistent characters.
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="text-muted-foreground rounded-xl border py-16 text-center text-sm">
          No projects match those filters.
        </div>
      ) : (
        <div className="divide-border overflow-hidden rounded-xl border">
          {filteredProjects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="hover:bg-muted flex items-center justify-between gap-4 border-b px-4 py-3 transition-colors last:border-b-0"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{p.title}</p>
                {p.description && (
                  <p className="text-muted-foreground truncate text-xs">
                    {p.description}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-muted-foreground font-data text-xs">
                  {p.aspect_ratio} \u00b7 {p.resolution}
                </span>
                <ProjectStatusBadge status={p.status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function NewProjectDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onCreate() {
    if (!title.trim()) {
      toast.error("Give the project a title.");
      return;
    }
    setSubmitting(true);
    try {
      const project = await createProject({
        title,
        description: description || undefined,
      });
      setOpen(false);
      setTitle("");
      setDescription("");
      router.push(`/projects/${project.id}`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Couldn't create the project.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          New project
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Project title"
            maxLength={200}
          />
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            rows={3}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => void onCreate()} disabled={submitting}>
            {submitting ? "Creating\u2026" : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
