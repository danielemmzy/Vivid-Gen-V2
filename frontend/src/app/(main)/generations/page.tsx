import { listGenerations } from "~/actions/generation";
import { GenerationsLibrary } from "~/components/generations-library";

export default async function GenerationsPage() {
  // Backend only supports limit/offset pagination on GET /generations — no
  // server-side type/status filter or search (see
  // VIVID_GEN_FRONTEND_PROGRESS.md "Backend gaps"). We fetch a page and
  // filter client-side rather than pretending the server can do it.
  const { generations } = await listGenerations(100, 0);

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6">
        <h1 className="font-display text-3xl font-semibold">Generations</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Everything you've created, across every workflow.
        </p>
      </div>
      <GenerationsLibrary generations={generations} />
    </div>
  );
}
