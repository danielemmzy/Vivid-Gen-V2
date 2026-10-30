"use client";

import {
  Clapperboard,
  Coins,
  FileText,
  Film,
  Home,
  ImageIcon,
  Images,
  Languages,
  Link2,
  Megaphone,
  Mic,
  Package,
  Palette,
  Scissors,
  Sparkles,
  UserRound,
  Volume2,
  Wand2,
  Youtube,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "../ui/sidebar";

/**
 * Every entry here maps to a verified backend capability — see
 * VIVID_GEN_FRONTEND_PROGRESS.md section 1 (V1) and
 * V2_ARCHITECTURE_AUDIT.md (V2 orchestration/workflows) for the endpoint
 * each one calls.
 */
type NavItem = {
  title: string;
  url: string;
  icon: typeof Home;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { title: "Home", url: "/dashboard", icon: Home },
      { title: "Create", url: "/create", icon: Sparkles },
      { title: "Generations", url: "/generations", icon: Film },
      { title: "Projects", url: "/projects", icon: Clapperboard },
    ],
  },
  {
    label: "Workflows",
    items: [
      { title: "Ad Studio", url: "/create/ads", icon: Megaphone },
      { title: "YouTube", url: "/create/youtube", icon: Youtube },
      { title: "Product Video", url: "/create/product-video", icon: Package },
      { title: "From URL", url: "/create/url-to-video", icon: Link2 },
      { title: "Podcast \u2192 Video", url: "/create/podcast", icon: Mic },
      { title: "Presentation \u2192 Video", url: "/create/presentation", icon: FileText },
      { title: "Video \u2192 Shorts", url: "/create/shorts", icon: Scissors },
    ],
  },
  {
    label: "Advanced",
    items: [
      { title: "Text \u2192 Video", url: "/create/text-to-video", icon: Wand2 },
      { title: "Image \u2192 Video", url: "/create/image-to-video", icon: ImageIcon },
      { title: "Text \u2192 Image", url: "/create/text-to-image", icon: ImageIcon },
      // gap-closure: these two pages existed and worked
      // (app/(main)/create/dubbing, .../image-to-image) but were
      // reachable only by typing the URL directly — not in any nav.
      { title: "Image \u2192 Image", url: "/create/image-to-image", icon: Images },
      { title: "Dubbing", url: "/create/dubbing", icon: Languages },
      { title: "Avatar", url: "/create/avatar", icon: UserRound },
      { title: "Video Translation", url: "/create/translate", icon: Languages },
      { title: "Audio Replace", url: "/create/audio-replace", icon: Volume2 },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "Credits", url: "/credits", icon: Coins },
      { title: "Brand Kits", url: "/brand-kits", icon: Palette },
    ],
  },
];

export default function SidebarMenuItems() {
  const path = usePathname();

  return (
    <>
      {NAV_GROUPS.map((group) => (
        <SidebarGroup key={group.label}>
          <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {group.items.map((item) => {
                const active = path === item.url;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild isActive={active}>
                      <Link href={item.url}>
                        <item.icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
    </>
  );
}
