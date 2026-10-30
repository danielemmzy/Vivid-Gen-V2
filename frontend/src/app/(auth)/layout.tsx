import "~/styles/globals.css";

import { type Metadata } from "next";
import { Bricolage_Grotesque, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";

import { Toaster } from "~/components/ui/sonner";
import { Providers } from "~/components/providers";
import { ThemeProvider } from "~/components/theme-provider";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage" });
const instrument = Instrument_Sans({ subsets: ["latin"], variable: "--font-instrument" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "Vivid Gen",
  description: "Vivid Gen is a modern AI-powered content generation platform that helps creators and businesses generate high-quality text, images, and digital assets faster. Built with a scalable full-stack architecture for speed, security, and performance.",
  icons: [{ rel: "icon", url: "/favicon.ico" }],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${instrument.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <body className="flex min-h-svh flex-col items-center justify-center">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <Providers>
            {children}
            <Toaster />
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}