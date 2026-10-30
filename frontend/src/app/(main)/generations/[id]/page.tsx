import { getGeneration } from "~/actions/generation";
import { GenerationDetail } from "~/components/generation-detail";

export default async function GenerationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const generation = await getGeneration(id);
  return (
    <div className="mx-auto max-w-4xl p-6">
      <GenerationDetail initial={generation} />
    </div>
  );
}
