import { getProject } from "~/actions/projects";
import { getModelCatalog } from "~/actions/models";
import { ProjectDetail } from "~/components/projects/project-detail";

export default async function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, { models }] = await Promise.all([getProject(id), getModelCatalog()]);
  const isStoryboard = project.status === "awaiting_approval" && Boolean(project.production_plan);
  return (
    <div className={isStoryboard ? "w-full p-3 sm:p-5 lg:p-6" : "mx-auto max-w-3xl p-6"}>
      <ProjectDetail project={project} models={models} />
    </div>
  );
}
