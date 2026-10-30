import { YoutubeForm } from "~/components/create/youtube-form";

export default function YoutubePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">YouTube</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Give the Director a topic \u2014 it plans a long-form script and storyboard.
        </p>
      </div>
      <YoutubeForm />
    </div>
  );
}
