import { ShortsForm } from "~/components/create/shorts-form";

export default function ShortsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Video \u2192 Shorts</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Vivid transcribes your video, finds the strongest moments, and cuts vertical clips \u2014 no fixed-interval slicing.
        </p>
      </div>
      <ShortsForm />
    </div>
  );
}
