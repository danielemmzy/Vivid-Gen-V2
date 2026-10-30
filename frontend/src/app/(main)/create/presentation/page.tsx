import { PresentationForm } from "~/components/create/presentation-form";

export default function PresentationPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Presentation \u2192 Video</h1>
        <p className="text-muted-foreground mt-1 text-sm">Upload a .pptx \u2014 Vivid reads the slide text and narrates it.</p>
      </div>
      <PresentationForm />
    </div>
  );
}
