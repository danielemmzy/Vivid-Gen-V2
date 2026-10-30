import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { listGenerations } from "~/actions/generation";
import { getCreditBalance, getCreditTransactions } from "~/actions/credits";
import { listProjects } from "~/actions/projects";
import { HomeDashboard } from "~/components/home/home-dashboard";

export default async function Page() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");

  const [{ generations }, balance, { transactions }, { projects }] = await Promise.all([
    listGenerations(50, 0),
    getCreditBalance(),
    getCreditTransactions(),
    listProjects(),
  ]);

  return (
    <HomeDashboard
      user={{ name: session.user.name, email: session.user.email, image: session.user.image ?? null }}
      generations={generations}
      balance={balance}
      transactions={transactions}
      projectsCount={projects.length}
      projects={projects}
    />
  );
}
