import { UrlToVideoForm } from "~/components/create/url-to-video-form";

export default function UrlToVideoPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">From URL</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Read the source, shape the story in your own words, then turn it into
          an editable video plan.
        </p>
      </div>
      <UrlToVideoForm />
    </div>
  );
}
