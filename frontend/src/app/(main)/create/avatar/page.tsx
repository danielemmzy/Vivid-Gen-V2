import { AvatarForm } from "~/components/create/avatar-form";

export default function AvatarPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="rounded-2xl border border-border bg-gradient-to-br from-primary/[0.08] via-card to-card p-5 sm:p-6">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Create · Avatar</p>
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Animate a portrait with speech</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">Turn a speaker photo and audio into a talking portrait. The estimate uses the audio duration when available.</p>
      </div>
      <AvatarForm />
    </div>
  );
}
