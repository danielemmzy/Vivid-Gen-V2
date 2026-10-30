import { Suspense } from "react";
import { TextToVideoForm } from "~/components/create/text-to-video-form";

export default function TextToVideoPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-primary/[0.10] via-card to-card p-5 sm:p-7">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Creation studio · Text-led movie</p>
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Turn a brief into an editable movie</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">Plan scenes, review the visual sequence, edit narration, captions, audio and branding, then approve the production budget before rendering.</p>
      </div>
      <Suspense><TextToVideoForm /></Suspense>
    </div>
  );
}
