import "~/styles/globals.css";

import { type Metadata } from "next";
import { Geist, Inter } from "next/font/google";

import { Toaster } from "~/components/ui/sonner";

import { Providers } from "~/components/providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Vivid Gen",
  description: "Vivid Gen is a modern AI-powered content generation platform that helps creators and businesses generate high-quality text, images, and digital assets faster. Built with a scalable full-stack architecture for speed, security, and performance.",
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
    <html lang="en" className={`${geist.variable} `}>
      <body className="flex min-h-svh flex-col items-center justify-center">
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}