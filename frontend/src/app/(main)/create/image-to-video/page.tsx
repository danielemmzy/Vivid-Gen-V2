import { ImageToVideoForm } from "~/components/create/image-to-video-form";

export default function ImageToVideoPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-primary/[0.10] via-card to-card p-5 sm:p-7">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Creation studio · Image-led movie</p>
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Turn a reference image into a story</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">Plan multiple shots around your visual reference. Edit the storyboard, sound, captions and brand treatment before you start rendering.</p>
      </div>
      <ImageToVideoForm />
    </div>
  );
}
