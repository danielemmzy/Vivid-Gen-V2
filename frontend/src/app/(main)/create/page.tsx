import {
  ArrowUpRight,
  AudioLines,
  Clapperboard,
  FileVideo2,
  ImageIcon,
  Languages,
  Link2,
  Megaphone,
  Mic2,
  Package,
  Presentation,
  Scissors,
  UserRound,
  type LucideIcon,
  Youtube,
} from "lucide-react";
import Link from "next/link";
import { DirectorPromptForm } from "~/components/create/director-prompt-form";

const workflows: { href: string; label: string; description: string; icon: LucideIcon }[] = [
  { href: "/create/ads", icon: Megaphone, label: "Ad Studio", description: "A complete campaign from product to finished ad." },
  { href: "/create/youtube", icon: Youtube, label: "YouTube", description: "Build a long form video from a topic or outline." },
  { href: "/create/product-video", icon: Package, label: "Product video", description: "Show your product using its real details and imagery." },
  { href: "/create/url-to-video", icon: Link2, label: "From a URL", description: "Turn an article into a fact grounded video script." },
  { href: "/create/podcast", icon: Mic2, label: "Podcast video", description: "Create a visual sequence around an audio recording." },
  { href: "/create/presentation", icon: Presentation, label: "Presentation", description: "Narrate and animate a PowerPoint deck." },
  { href: "/create/shorts", icon: Scissors, label: "Shorts", description: "Find strong moments in a long video and shape them for social." },
  { href: "/create/dubbing", icon: Languages, label: "Dubbing", description: "Translate spoken video and preserve lip movement." },
];

const tools: { href: string; label: string; icon: LucideIcon; description: string }[] = [
  { href: "/create/text-to-video", label: "Text to video", icon: FileVideo2, description: "Generate a video clip directly from a prompt." },
  { href: "/create/image-to-video", label: "Image to video", icon: ImageIcon, description: "Animate a still image with camera and motion direction." },
  { href: "/create/text-to-image", label: "Text to image", icon: ImageIcon, description: "Create a key visual from a prompt." },
  { href: "/create/image-to-image", label: "Image variations", icon: ImageIcon, description: "Create a new visual from an image reference." },
  { href: "/create/avatar", label: "Avatar", icon: UserRound, description: "Create a presenter led video." },
  { href: "/create/translate", label: "Video translate", icon: Languages, description: "Localize a video for a new audience." },
  { href: "/create/audio-replace", label: "Audio replace", icon: AudioLines, description: "Replace the soundtrack of an existing video." },
];

export default async function CreatePage({ searchParams }: { searchParams?: Promise<{ prompt?: string }> }) {
  const params = searchParams ? await searchParams : {};
  const initialPrompt = typeof params.prompt === "string" ? params.prompt : "";

  return (
    <div className="studio-create-page mx-auto max-w-[1160px] space-y-10 px-5 py-8 sm:px-8 sm:py-10">
      <header className="studio-create-heading">
        <div><span className="studio-eyebrow">CREATION STUDIO</span><h1 className="font-display mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">What are we making?</h1></div>
        <span className="studio-create-mark"><Clapperboard className="size-5" /></span>
      </header>

      <section className="studio-director-panel">
        <div className="studio-panel-heading"><span className="studio-card-icon"><Clapperboard className="size-5" /></span><div><h2>AI Director</h2><span>Start with an idea</span></div></div>
        <DirectorPromptForm initialPrompt={initialPrompt} />
      </section>

      <section>
        <div className="studio-section-head"><h2>Guided workflows</h2><span className="studio-count">{workflows.length} workflows</span></div>
        <div className="studio-create-grid">
          {workflows.map(({ href, label, description, icon: Icon }) => (
            <Link href={href} key={href} className="studio-create-card" aria-label={`${label}. ${description}`}>
              <span className="studio-card-icon"><Icon className="size-[19px]" /></span><span className="studio-create-label">{label}</span><ArrowUpRight className="studio-card-arrow size-4" />
              <span className="studio-workflow-tooltip" role="tooltip">{description}</span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="studio-section-head"><h2>Direct generation</h2><span className="studio-count">7 tools</span></div>
        <div className="studio-tool-list">
          {tools.map(({ href, label, description, icon: Icon }) => (
            <Link href={href} key={href} className="studio-tool-link" aria-label={`${label}. ${description}`}>
              <Icon className="size-4" /><span>{label}</span><span className="studio-workflow-tooltip" role="tooltip">{description}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
