"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

const animations = {
  camera: "https://assets-v2.lottiefiles.com/a/9eb8628c-03ca-11ef-a801-93f3ff8abe8c/F7sVQFShS0.lottie",
  sparkle: "https://assets-v2.lottiefiles.com/a/d11495f2-1177-11ee-b956-933b86b055db/C020as4J9V.lottie",
};

export function LottieMark({ kind, className = "" }: { kind: keyof typeof animations; className?: string }) {
  const [motionAllowed, setMotionAllowed] = useState(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setMotionAllowed(!preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  return <span className={`vivid-lottie ${className}`} aria-hidden="true">
    <Script src="https://unpkg.com/@lottiefiles/dotlottie-wc@0.6.2/dist/dotlottie-wc.js" type="module" strategy="afterInteractive" />
    <dotlottie-wc src={animations[kind]} autoplay={motionAllowed ? "true" : undefined} loop="true" />
  </span>;
}
