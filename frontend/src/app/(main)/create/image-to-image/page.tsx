import { getModelCatalog } from "~/actions/models";
import { ImageToImageForm } from "~/components/create/image-to-image-form";

export default async function ImageToImagePage() {
  const { models } = await getModelCatalog();
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-primary/[0.08] via-card to-card p-5 sm:p-6">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Create · Image editing</p>
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Edit or restyle an image</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">Upload a source image, describe the change and review the model-specific credit estimate before generation.</p>
      </div>
      <ImageToImageForm models={models.filter((model) => model.type === "image_to_image")} />
    </div>
  );
}
