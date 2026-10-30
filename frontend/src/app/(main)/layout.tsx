import "~/styles/globals.css";

import { type Metadata } from "next";
import { Bricolage_Grotesque, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";

import { Toaster } from "~/components/ui/sonner";
import { cn } from "~/lib/utils";
import { Providers } from "~/components/providers";
import { ThemeProvider } from "~/components/theme-provider";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "~/components/ui/sidebar";
import { AppSidebar } from "~/components/sidebar/app-sidebar";
import { Separator } from "~/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
} from "~/components/ui/breadcrumb";
import BreadcrumbClient from "~/components/sidebar/breadcrumb-client";
import { ThemeToggle } from "~/components/theme-toggle";

// Signature typefaces — see VIVID_GEN_FRONTEND_PROGRESS.md and
// styles/globals.css for why these three and not Inter/Geist/Roboto.
const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
});
const instrument = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Vivid Gen",
  description:
    "Vivid Gen is a modern AI-powered content generation platform that helps creators and businesses generate high-quality text, images, and digital assets faster. Built with a scalable full-stack architecture for speed, security, and performance.",
  icons: [{ rel: "icon", url: "/favicon.ico" }],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={cn(bricolage.variable, instrument.variable, plexMono.variable)}
      suppressHydrationWarning
    >
      <body className="min-h-svh">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <Providers>
            <Toaster />
            <SidebarProvider defaultOpen={true}>
              <AppSidebar />
              <SidebarInset className="flex h-svh flex-col">
                <header className="bg-background/80 sticky top-0 z-10 flex items-center justify-between gap-2 border-b px-4 py-2 backdrop-blur">
                  <div className="flex shrink-0 grow items-center gap-2">
                    <SidebarTrigger className="-ml-1" />
                    <Separator
                      orientation="vertical"
                      className="mr-2 data-[orientation=vertical]:h-4"
                    />
                    <Breadcrumb>
                      <BreadcrumbList>
                        <BreadcrumbItem>
                          <BreadcrumbClient />
                        </BreadcrumbItem>
                      </BreadcrumbList>
                    </Breadcrumb>
                  </div>
                  <ThemeToggle />
                </header>
                <main className="flex-1 overflow-y-auto">{children}</main>
              </SidebarInset>
            </SidebarProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
