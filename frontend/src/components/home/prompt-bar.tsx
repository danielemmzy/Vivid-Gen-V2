"use client";

import { ArrowUpRight, ImageIcon, Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { cn } from "~/lib/utils";

const QUICK_TYPES = [
  { value: "text-to-video", label: "Text to Video", route: "/create/text-to-video" },
  { value: "text-to-image", label: "Text to Image", route: "/create/text-to-image" },
] as const;

export function HomePromptBar() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState<(typeof QUICK_TYPES)[number]["value"]>("text-to-video");

  function submit() {
    const route = QUICK_TYPES.find((t) => t.value === type)!.route;
    const query = prompt.trim() ? `?prompt=${encodeURIComponent(prompt.trim())}` : "";
    router.push(`${route}${query}`);
  }

  return (
    <div className="studio-prompt-shell">
      <Select value={type} onValueChange={(v) => setType(v as typeof type)}>
        <SelectTrigger className="w-full border-0 bg-transparent shadow-none sm:w-48">
          {type === "text-to-video" ? <Wand2 className="size-4" /> : <ImageIcon className="size-4" />}
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {QUICK_TYPES.map((t) => (
            <SelectItem key={t.value} value={t.value}>
              {t.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <input
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="Describe what you have in mind…"
        className="text-foreground placeholder:text-muted-foreground min-h-12 flex-1 bg-transparent px-3 py-2 text-[15px] outline-none"
      />
      <button
        onClick={submit}
        className={cn(
          "studio-submit-button",
        )}
        aria-label="Open generation studio"
      >
        <span>Create</span>
        <ArrowUpRight className="size-4" />
      </button>
    </div>
  );
}
