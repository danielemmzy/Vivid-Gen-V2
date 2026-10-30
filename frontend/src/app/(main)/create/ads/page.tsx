import { AdsForm } from "~/components/create/ads-form";

export default function AdsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Ad Studio</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Tell the Director about your product \u2014 it plans the hook, script, and shots.
        </p>
      </div>
      <AdsForm />
    </div>
  );
}
