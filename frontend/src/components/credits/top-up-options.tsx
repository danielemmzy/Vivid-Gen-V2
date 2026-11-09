/* eslint-disable @typescript-eslint/no-unsafe-call */
"use client";

import { useState } from "react";
import { Coins, Loader2, ShoppingCart } from "lucide-react";
import { toast } from "sonner";
import { authClient } from "~/lib/auth-client";
import type { CreditPackage } from "~/actions/credits";
import { Button } from "~/components/ui/button";

export function TopUpOptions({
  packages,
  configured,
  message,
}: {
  packages: CreditPackage[];
  configured: boolean;
  message: string | null;
}) {
  const [pending, setPending] = useState<string | null>(null);
  async function checkout(key: string, productId: string) {
    setPending(key);
    try {
      await authClient.checkout({ products: [productId] });
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Couldn't start checkout. Please try again.",
      );
    } finally {
      setPending(null);
    }
  }

  if (!configured || packages.length === 0)
    return (
      <p className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm">
        {message ?? "Credit packs are not configured yet."}
      </p>
    );
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {packages.map((pack) => (
        <div
          key={pack.key}
          className={`hover:border-primary/50 relative flex flex-col rounded-2xl border p-4 transition-colors ${pack.key === "medium" ? "border-primary/50 bg-primary/[0.04]" : "border-border bg-card"}`}
        >
          {pack.key === "medium" && (
            <span className="bg-primary/10 text-primary absolute top-3 right-3 rounded-full px-2 py-1 text-[10px] font-semibold">
              POPULAR
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-xl">
              <Coins className="size-4" />
            </span>
            <p className="font-semibold">{pack.title}</p>
          </div>
          <p className="font-display mt-4 text-3xl font-semibold tabular-nums">
            {pack.credits}
            <span className="text-muted-foreground ml-1 text-sm font-normal">
              credits
            </span>
          </p>
          <p className="text-muted-foreground mt-1 min-h-8 text-xs">
            {pack.price_usd > 0
              ? `$${pack.price_usd.toFixed(2)} · `
              : "Price shown at checkout · "}
            {pack.key === "small"
              ? "Try a few creations"
              : pack.key === "medium"
                ? "More room to iterate"
                : "For bigger production days"}
          </p>
          <Button
            className="mt-4 w-full"
            variant={pack.key === "medium" ? "default" : "outline"}
            disabled={pending !== null}
            onClick={() => void checkout(pack.key, pack.product_id)}
          >
            {pending === pack.key ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <ShoppingCart className="mr-2 size-4" />
            )}
            {pending === pack.key ? "Opening checkout…" : "Top up credits"}
          </Button>
        </div>
      ))}
    </div>
  );
}
