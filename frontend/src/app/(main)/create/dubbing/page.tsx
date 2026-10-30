import { DubbingForm } from "~/components/create/dubbing-form";

export default function DubbingPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Dubbing</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Translate a video into another language with lip-sync \u2014 this uses the same Video Translation engine as the Advanced tools tab.
        </p>
      </div>
      <DubbingForm />
    </div>
  );
}
