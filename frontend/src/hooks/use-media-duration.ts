"use client";

/** Read local audio/video metadata so quote and reservation use source duration. */
export function readMediaDuration(file: File): Promise<number | null> {
  if (typeof window === "undefined" || !file.type.startsWith("audio/") && !file.type.startsWith("video/")) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    const objectUrl = URL.createObjectURL(file);
    const media = document.createElement(file.type.startsWith("audio/") ? "audio" : "video");
    media.preload = "metadata";
    const cleanup = () => URL.revokeObjectURL(objectUrl);
    media.onloadedmetadata = () => {
      const seconds = media.duration;
      cleanup();
      resolve(Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null);
    };
    media.onerror = () => {
      cleanup();
      resolve(null);
    };
    media.src = objectUrl;
  });
}
