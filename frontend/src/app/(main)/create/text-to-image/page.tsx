import { Suspense } from "react";
import { getModelCatalog } from "~/actions/models";
import { TextToImageForm } from "~/components/create/text-to-image-form";

export default async function TextToImagePage() {
  const { models } = await getModelCatalog();
  const options = models.filter((m) => m.type === "text_to_image");
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Text \u2192 Image</h1>
        <p className="text-muted-foreground mt-1 text-sm">Generate an image from a text prompt.</p>
      </div>
      <Suspense>
        <TextToImageForm models={options} />
      </Suspense>
    </div>
  );
}
