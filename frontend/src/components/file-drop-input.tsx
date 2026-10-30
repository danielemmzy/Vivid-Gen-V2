"use client";

import { UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { cn } from "~/lib/utils";

export function FileDropInput({
  accept,
  label,
  onFile,
  preview,
}: {
  accept: string;
  label: string;
  onFile: (file: File | null) => void;
  /** "image" shows a thumbnail preview; "video"/"audio" show the file name only. */
  preview?: "image" | "video" | "audio";
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleFile(file: File | null) {
    setFileName(file?.name ?? null);
    setPreviewUrl(file ? URL.createObjectURL(file) : null);
    onFile(file);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
      }}
      onClick={() => inputRef.current?.click()}
      className={cn(
        "border-border hover:border-foreground/30 flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-4 text-center transition-colors",
        dragOver && "border-foreground/50 bg-muted",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
      />
      {previewUrl && preview === "image" ? (
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={previewUrl} alt="" className="max-h-40 rounded-md object-contain" />
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleFile(null);
            }}
            className="bg-background absolute -top-2 -right-2 rounded-full border p-1"
            aria-label="Remove file"
          >
            <X className="size-3" />
          </button>
        </div>
      ) : fileName ? (
        <p className="text-sm">{fileName}</p>
      ) : (
        <>
          <UploadCloud className="text-muted-foreground size-5" />
          <p className="text-muted-foreground text-xs">{label}</p>
        </>
      )}
    </div>
  );
}
