import { PodcastForm } from "~/components/create/podcast-form";

export default function PodcastPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">
          Podcast \u2192 Video
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Upload audio \u2014 Vivid transcribes it and plans visuals around
          what&apos;s said.
        </p>
      </div>
      <PodcastForm />
    </div>
  );
}
