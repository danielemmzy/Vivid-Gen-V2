import "~/styles/globals.css";

import { type Metadata } from "next";
import { Geist, Inter } from "next/font/google";

import { Toaster } from "~/components/ui/sonner";
import { cn } from "~/lib/utils";
import { Providers } from "~/components/providers";
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

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Vivid Gen",
  description:
    "Vivid Gen is a modern AI-powered content generation platform that helps creators and businesses generate high-quality text, images, and digital assets faster. Built with a scalable full-stack architecture for speed, security, and performance.",
  icons: [{ rel: "icon", url: "/favicon.ico" }],
};

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={cn(geist.variable, inter.variable)}>
      <body className="flex min-h-svh flex-col items-center justify-center">
        <Providers>
          <Toaster />
          <SidebarProvider defaultOpen={false}>
            <AppSidebar />
            <SidebarInset className="flex h-screen flex-col">
              <header className="bg-backgroung sticky-top z-10 border-b px-4 py-2">
                <div className="gap2 flex shrink-0 grow items-center">
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
              </header>
              <main className="flex-1 overflow-y-auto">{children}</main>
            </SidebarInset>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  );
}
