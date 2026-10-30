import { listProjects } from "~/actions/projects";
import { ProjectsList } from "~/components/projects/projects-list";

export default async function ProjectsPage() {
  const { projects } = await listProjects();
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-3xl font-semibold">Projects</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Storyboard-driven video: define characters once, then generate consistent shots and assemble them.
        </p>
      </div>
      <ProjectsList projects={projects} />
    </div>
  );
}
