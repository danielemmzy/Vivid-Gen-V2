"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

// next-themes was already a dependency but was never wired up — the app
// had no way to switch themes despite a full light-mode palette existing
// in globals.css. Dark is the brand default (see design tokens doc).
export function ThemeProvider({
  children,
  ...props
}: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
