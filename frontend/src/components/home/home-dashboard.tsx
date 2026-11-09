import { formatDistanceToNow } from "date-fns/formatDistanceToNow";
import {
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Clapperboard,
  Coins,
  Film,
  ImageIcon,
  LoaderCircle,
  Mic2,
  Package,
  Play,
  Sparkles,
  Video,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { CreditBalance, CreditTransaction } from "~/actions/credits";
import type { GenerationResult } from "~/actions/generation";
import type { Project } from "~/actions/projects";
import {
  GenerationStatusBadge,
  isInFlight,
} from "~/components/generation-status-badge";
import { HomePromptBar } from "~/components/home/prompt-bar";
import { LottieMark } from "~/components/lottie-mark";
import { TYPE_LABELS } from "~/lib/generation-types";

const quickStarts: {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  meta: string;
}[] = [
  {
    href: "/create",
    label: "AI Director",
    hint: "Turn a brief into a complete scene plan, then approve the production.",
    icon: WandSparkles,
    meta: "Recommended",
  },
  {
    href: "/create/image-to-video",
    label: "Image to video",
    hint: "Bring a still image to life with motion and camera direction.",
    icon: ImageIcon,
    meta: "Reference led",
  },
  {
    href: "/create/text-to-image",
    label: "Image studio",
    hint: "Create a key visual or explore an art direction.",
    icon: Sparkles,
    meta: "Image",
  },
  {
    href: "/create/podcast",
    label: "Audio to video",
    hint: "Build a visual sequence around a recording, voice or music.",
    icon: AudioLines,
    meta: "Audio",
  },
];

const workflows: {
  href: string;
  label: string;
  detail: string;
  icon: LucideIcon;
}[] = [
  {
    href: "/create/ads",
    label: "Ad Studio",
    detail: "A product and audience into a finished ad",
    icon: Video,
  },
  {
    href: "/create/youtube",
    label: "YouTube",
    detail: "A topic into a long form video",
    icon: Play,
  },
  {
    href: "/create/product-video",
    label: "Product video",
    detail: "A product story built from your details",
    icon: Package,
  },
  {
    href: "/create/url-to-video",
    label: "From a URL",
    detail: "An article into a grounded script",
    icon: ArrowRight,
  },
  {
    href: "/create/presentation",
    label: "Presentation",
    detail: "Narration and scenes from a slide deck",
    icon: Clapperboard,
  },
  {
    href: "/create/shorts",
    label: "Shorts",
    detail: "Find the strongest moments in a video",
    icon: Film,
  },
  {
    href: "/create/dubbing",
    label: "Dubbing",
    detail: "Translate speech with lip sync",
    icon: Mic2,
  },
  {
    href: "/create/translate",
    label: "Video translate",
    detail: "Localize a video for another audience",
    icon: AudioLines,
  },
];

export function HomeDashboard({
  user,
  generations,
  balance,
  transactions,
  projectsCount,
  projects = [],
}: {
  user: { name: string; email: string; image: string | null };
  generations: GenerationResult[];
  balance: CreditBalance;
  transactions: CreditTransaction[];
  projectsCount: number;
  projects?: Project[];
}) {
  const firstName = user.name.split(" ")[0] ?? user.name;
  const inFlight = generations.filter((item) => isInFlight(item.status));

  return (
    <div className="studio-dashboard mx-auto max-w-[1440px] space-y-9 px-5 py-7 sm:px-8 sm:py-9">
      <section className="studio-welcome">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <span className="studio-eyebrow">
              <LottieMark kind="sparkle" /> YOUR CREATIVE STUDIO
            </span>
            <h1 className="font-display mt-2 text-3xl font-semibold tracking-tight sm:text-[2.65rem]">
              Welcome back, {firstName}
            </h1>
          </div>
          <Link href="/create" className="studio-text-link">
            Open director <ArrowUpRight className="size-4" />
          </Link>
        </div>
        <div className="mt-7">
          <HomePromptBar />
        </div>
      </section>

      <section aria-labelledby="quick-starts-title">
        <div className="studio-section-head">
          <h2 id="quick-starts-title">Start creating</h2>
          <Link href="/create" className="studio-text-link">
            All workflows <ArrowRight className="size-4" />
          </Link>
        </div>
        <div className="studio-quick-grid">
          {quickStarts.map(({ href, label, hint, icon: Icon, meta }) => (
            <Link
              className="studio-quick-card group"
              href={href}
              key={href}
              aria-label={`${label}. ${hint}`}
            >
              <span className="studio-card-icon">
                <Icon className="size-[19px]" />
              </span>
              <span className="studio-card-label">{label}</span>
              <span className="studio-card-meta">{meta}</span>
              <span className="studio-hover-note" role="tooltip">
                {hint}
              </span>
              <ArrowUpRight
                className="studio-card-arrow size-4"
                aria-hidden="true"
              />
            </Link>
          ))}
        </div>
      </section>

      <section aria-labelledby="workflows-title">
        <div className="studio-section-head">
          <h2 id="workflows-title">More ways to create</h2>
          <span className="studio-count">12 options</span>
        </div>
        <div className="studio-workflow-grid">
          {workflows.map(({ href, label, detail, icon: Icon }) => (
            <Link
              className="studio-workflow-link"
              href={href}
              key={href}
              aria-label={`${label}. ${detail}`}
            >
              <Icon className="size-4" aria-hidden="true" />
              <span>{label}</span>
              <span className="studio-workflow-tooltip" role="tooltip">
                {detail}
              </span>
            </Link>
          ))}
          {[
            [
              "Text to video",
              "/create/text-to-video",
              "Generate a clip directly from a written prompt",
            ],
            [
              "Image to image",
              "/create/image-to-image",
              "Create a new image variation from a reference",
            ],
            ["Avatar", "/create/avatar", "Create a presenter led video"],
            [
              "Audio replace",
              "/create/audio-replace",
              "Replace the soundtrack while keeping the video",
            ],
          ].map(([label, href, detail]) => (
            <Link
              className="studio-workflow-link"
              href={href!}
              key={href}
              aria-label={`${label}. ${detail}`}
            >
              <Sparkles className="size-4" aria-hidden="true" />
              <span>{label}</span>
              <span className="studio-workflow-tooltip" role="tooltip">
                {detail}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="studio-metrics" aria-label="Workspace overview">
        <Metric
          icon={Coins}
          label="Credits"
          value={balance.credits.toLocaleString()}
          href="/credits"
        />
        <Metric
          icon={Film}
          label="Generations"
          value={generations.length >= 50 ? "50+" : String(generations.length)}
          href="/generations"
        />
        <Metric
          icon={LoaderCircle}
          label="Processing"
          value={String(inFlight.length)}
          pulse={inFlight.length > 0}
          href="/generations"
        />
        <Metric
          icon={Clapperboard}
          label="Projects"
          value={String(projectsCount)}
          href="/projects"
        />
      </section>

      <section className="grid gap-7 xl:grid-cols-[1.15fr_.85fr]">
        <div className="studio-data-panel">
          <div className="studio-section-head">
            <h2>Recent projects</h2>
            <Link href="/projects" className="studio-text-link">
              View all <ArrowRight className="size-4" />
            </Link>
          </div>
          {projects.length === 0 ? (
            <Link
              className="studio-empty-state"
              href="/create"
              aria-label="Create your first storyboard project"
            >
              <Clapperboard className="size-5" />
              <span>Your first project starts here</span>
              <ArrowRight className="ml-auto size-4" />
              <span className="studio-hover-note" role="tooltip">
                Plan a film, review its scenes and export a finished cut.
              </span>
            </Link>
          ) : (
            <div className="studio-project-list">
              {projects.slice(0, 5).map((project) => (
                <Link
                  key={project.id}
                  className="studio-project-row"
                  href={`/projects/${project.id}`}
                  title={
                    project.description ??
                    `${project.aspect_ratio} · ${project.resolution} storyboard project`
                  }
                >
                  <span className="studio-project-icon">
                    <Clapperboard className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {project.title}
                    </span>
                    <span className="studio-project-meta">
                      {project.production_plan?.duration_seconds
                        ? `${project.production_plan.duration_seconds}s`
                        : project.aspect_ratio}{" "}
                      · {project.status.replaceAll("_", " ")}
                    </span>
                  </span>
                  <ArrowUpRight className="text-muted-foreground size-4" />
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="studio-data-panel">
          <div className="studio-section-head">
            <h2>Recent generations</h2>
            <Link href="/generations" className="studio-text-link">
              View all <ArrowRight className="size-4" />
            </Link>
          </div>
          {generations.length === 0 ? (
            <Link
              className="studio-empty-state"
              href="/create"
              aria-label="Start your first generation"
            >
              <Sparkles className="size-5" />
              <span>No generations yet</span>
              <ArrowRight className="ml-auto size-4" />
              <span className="studio-hover-note" role="tooltip">
                Your finished and in-progress media will appear here.
              </span>
            </Link>
          ) : (
            <div className="studio-project-list">
              {generations.slice(0, 5).map((item) => (
                <Link
                  key={item.id}
                  href={`/generations/${item.id}`}
                  className="studio-project-row"
                >
                  <span className="studio-project-icon">
                    <Play className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {item.title ?? TYPE_LABELS[item.type] ?? item.type}
                    </span>
                    <span className="studio-project-meta">
                      {item.created_at
                        ? formatDistanceToNow(new Date(item.created_at), {
                            addSuffix: true,
                          })
                        : ""}
                    </span>
                  </span>
                  <GenerationStatusBadge status={item.status} />
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="studio-account-strip">
        <span className="studio-account-avatar">
          {user.image ? (
            <img src={user.image} alt="" />
          ) : (
            firstName.slice(0, 1).toUpperCase()
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            {user.name}
          </span>
          <span className="studio-project-meta">{user.email}</span>
        </span>
        <span className="studio-account-balance">
          <Coins className="size-4" />
          {balance.credits.toLocaleString()} credits
        </span>
        <Link href="/customer-portal" className="studio-text-link">
          Billing <ArrowUpRight className="size-4" />
        </Link>
      </section>
      <span className="sr-only">
        {transactions.length} recent credit transactions
      </span>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  href,
  pulse = false,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  href: string;
  pulse?: boolean;
}) {
  return (
    <Link
      className="studio-metric"
      href={href}
      title={label}
      aria-label={`${label}: ${value}`}
    >
      <Icon className={`size-4 ${pulse ? "animate-spin" : ""}`} />
      <span className="studio-metric-value">{value}</span>
      <span className="studio-metric-label">{label}</span>
    </Link>
  );
}
