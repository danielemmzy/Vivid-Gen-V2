import type React from "react";
import { formatDistanceToNow } from "date-fns/formatDistanceToNow";
import { Activity, Coins, Gauge, Sparkles } from "lucide-react";
import { getCreditBalance, getCreditTransactions, getCreditPackages } from "~/actions/credits";
import { getUsageSummary } from "~/actions/usage";
import { TopUpOptions } from "~/components/credits/top-up-options";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";

// Verified transaction types — backend/app/core/constants.py::CreditTransactionType.
// Anything not in this map still renders (falls back to the raw string) so a
// future backend addition never breaks the page.
const TYPE_LABELS: Record<string, string> = {
  GRANT: "Free credits",
  PURCHASE: "Purchase",
  SUBSCRIPTION_RENEWAL: "Subscription renewal",
  GENERATION_RESERVATION: "Reserved for generation",
  GENERATION_CHARGE: "Generation charge",
  GENERATION_REFUND: "Refund",
  ADMIN_ADJUSTMENT: "Adjustment",
};

export default async function CreditsPage() {
  const [{ credits, credit_usd_value }, { transactions }, usage, packages] = await Promise.all([
    getCreditBalance(),
    getCreditTransactions(),
    getUsageSummary(),
    getCreditPackages(),
  ]);
  const usagePercent = usage.monthly_video_seconds_limit > 0
    ? Math.min(100, (usage.video_seconds_used / usage.monthly_video_seconds_limit) * 100)
    : 100;

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6">
      <div>
        <h1 className="font-display text-3xl font-semibold">Credits</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Your balance and every reservation, charge, and refund against it.
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-muted-foreground text-sm font-normal">Current balance</CardTitle>
          <Coins className="text-muted-foreground size-4" />
        </CardHeader>
        <CardContent>
          <div className="font-data text-4xl font-medium">{credits.toLocaleString()}</div>
          <p className="text-muted-foreground mt-1 text-xs">
            \u2248 ${(credits * credit_usd_value).toFixed(2)} at ${credit_usd_value.toFixed(4)} / credit
          </p>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div className="flex items-center gap-2"><Sparkles className="text-primary size-4" /><h2 className="text-sm font-semibold">Top up credits</h2></div>
        <p className="text-muted-foreground text-sm">Choose a one-time credit pack. Your balance is updated from the verified payment event and recorded in the credit ledger.</p>
        <TopUpOptions packages={packages.packages} configured={packages.configured} message={packages.message} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2"><Activity className="text-primary size-4" /><h2 className="text-sm font-semibold">Plan & usage</h2></div>
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><p className="text-muted-foreground text-xs">Current entitlement</p><p className="mt-1 text-lg font-semibold">{usage.plan_label} plan</p></div>
              <div className="text-right"><p className="text-muted-foreground text-xs">Video seconds used / reserved</p><p className="font-data mt-1 text-lg font-semibold">{usage.video_seconds_used}s <span className="text-muted-foreground text-sm font-normal">/ {usage.monthly_video_seconds_limit}s</span></p></div>
            </div>
            <div className="bg-muted h-2 overflow-hidden rounded-full"><div className="bg-primary h-full rounded-full transition-[width]" style={{ width: `${usagePercent}%` }} /></div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <UsageMetric icon={<Gauge className="size-3.5" />} label="Remaining" value={`${usage.remaining_video_seconds}s`} />
              <UsageMetric icon={<Activity className="size-3.5" />} label="Active jobs" value={`${usage.active_generations} / ${usage.max_concurrent_generations}`} />
              <UsageMetric icon={<Coins className="size-3.5" />} label="Credit balance" value={usage.credits_balance.toLocaleString()} />
              <UsageMetric icon={<Sparkles className="size-3.5" />} label="Max movie length" value={`${usage.max_project_duration_seconds}s`} />
            </div>
            <p className="text-muted-foreground text-xs">Usage period starts {new Date(usage.period_start).toLocaleDateString()}. This figure includes completed output plus active plan duration reserved against your allowance; failed jobs are excluded. Credit packs add credits but do not automatically change your plan tier.</p>
          </CardContent>
        </Card>
      </section>

      <div>
        <h2 className="mb-3 text-sm font-medium">Transaction history</h2>
        {transactions.length === 0 ? (
          <Card>
            <CardContent className="text-muted-foreground py-10 text-center text-sm">
              No transactions yet. Your first generation will show up here.
            </CardContent>
          </Card>
        ) : (
          <div className="divide-border overflow-hidden rounded-xl border">
            {transactions.map((txn) => (
              <div
                key={txn.id}
                className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {TYPE_LABELS[txn.type] ?? txn.type}
                  </p>
                  <p className="text-muted-foreground truncate text-xs">
                    {txn.description ?? "\u2014"} \u00b7{" "}
                    {formatDistanceToNow(new Date(txn.created_at), { addSuffix: true })}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={cn(
                      "font-data text-sm font-medium",
                      txn.amount >= 0 ? "text-success" : "text-foreground",
                    )}
                  >
                    {txn.amount >= 0 ? "+" : ""}
                    {txn.amount.toLocaleString()}
                  </p>
                  <p className="text-muted-foreground font-data text-xs">
                    bal {txn.balance_after.toLocaleString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function UsageMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="rounded-xl border p-3"><div className="text-muted-foreground flex items-center gap-1.5 text-[10px] uppercase tracking-wide">{icon}{label}</div><p className="font-data mt-1 text-sm font-semibold">{value}</p></div>;
}
