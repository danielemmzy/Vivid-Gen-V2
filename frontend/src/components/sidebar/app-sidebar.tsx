import { UserButton } from "@daveyplate/better-auth-ui";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "../ui/sidebar";
import SidebarMenuItems from "./sidebar-menu-items";
import { Credits } from "./credits";

import Upgrade from "./upgrade";
import { User } from "lucide-react";

export async function AppSidebar() {
  return (
    <Sidebar>
      <SidebarHeader className="mt-2 mb-2 px-2">
        <p className="font-display text-2xl font-semibold tracking-tight uppercase">
          Vivid Gen
        </p>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenuItems />
      </SidebarContent>
      <SidebarFooter>
        <div className="mb-2 flex w-full items-center justify-center gap-1 text-xs">
          <Credits />
          <Upgrade />
        </div>
        <UserButton
          variant="outline"
          size="default"
          additionalLinks={[
            {
              label: "Customer Portal",
              href: "/customer-portal",
              icon: <User />,
            },
          ]}
        />
      </SidebarFooter>
    </Sidebar>
  );
}
