"use client";

import { useState } from "react";
import { getPresignedUrl } from "~/actions/generation";

/**
 * Same presign-then-PUT pattern already used in
 * components/modals/photo-to-video-modal.tsx, extracted so new Create
 * pages don't each reimplement it. Calls the verified
 * POST /uploads/presign endpoint, then PUTs directly to S3.
 */
export function useDirectUpload() {
  const [uploading, setUploading] = useState(false);

  async function upload(file: File, purpose: string): Promise<string> {
    setUploading(true);
    try {
      const { url, key } = await getPresignedUrl(file.name, file.type, purpose);
      await fetch(url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
      return key;
    } finally {
      setUploading(false);
    }
  }

  return { upload, uploading };
}
