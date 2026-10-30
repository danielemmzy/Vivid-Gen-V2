import { AudioReplaceForm } from "~/components/create/audio-replace-form";

export default function AudioReplacePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-primary/[0.08] via-card to-card p-5 sm:p-6">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Create · Audio replacement</p>
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Replace a video soundtrack</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">Upload a video and new audio track. Vivid estimates the cost using the source video duration before processing.</p>
      </div>
      <AudioReplaceForm />
    </div>
  );
}
