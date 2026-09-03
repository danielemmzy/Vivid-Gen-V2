import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { ClientHome } from "~/components/client-home";
import { auth } from "~/lib/auth";
import { listGenerations } from "~/actions/generation";
import { formatDistanceToNow } from "date-fns/formatDistanceToNow";

const TYPE_LABELS: Record<string, string> = {
  image_to_video: "Photo to Video",
  avatar: "Photo to Video",
  video_translation: "Translate Video",
  audio_replace: "Change Video Audio",
  text_to_image: "Text to Image",
  image_to_image: "Image to Image",
  text_to_video: "Text to Video",
};

export default async function Page() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");

  // Generations now live entirely in the FastAPI backend (core.generation)
  // — see the architecture plan's Decision 1. This replaces the old
  // three-table Prisma query with one call to the generation gateway.
  const { generations } = await listGenerations(20, 0);

  const recentCreations = generations.map((g) => ({
    id: g.id,
    title: g.title ?? TYPE_LABELS[g.type] ?? g.type,
    date: g.created_at ? formatDistanceToNow(new Date(g.created_at), { addSuffix: true }) : "",
    type: TYPE_LABELS[g.type] ?? g.type,
    videoUrl: g.status === "completed" ? g.output_url : null,
    status: g.status,
  }));

  return <ClientHome recentCreations={recentCreations} />;
}
