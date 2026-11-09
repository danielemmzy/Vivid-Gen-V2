"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  createBrandKit,
  deleteBrandKit,
  type BrandKit,
} from "~/actions/brand-kits";
import { FileDropInput } from "~/components/file-drop-input";
import { Button } from "~/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import { Input } from "~/components/ui/input";
import { useDirectUpload } from "~/hooks/use-direct-upload";

export function BrandKitsList({ brandKits }: { brandKits: BrandKit[] }) {
  const [kits, setKits] = useState(brandKits);

  async function onDelete(id: string) {
    const prev = kits;
    setKits((k) => k.filter((kit) => kit.id !== id));
    try {
      await deleteBrandKit(id);
    } catch (err) {
      setKits(prev);
      toast.error(
        err instanceof Error ? err.message : "Couldn't delete that brand kit.",
      );
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <NewBrandKitDialog onCreated={(kit) => setKits((k) => [kit, ...k])} />
      </div>

      {kits.length === 0 ? (
        <div className="text-muted-foreground rounded-xl border py-16 text-center text-sm">
          No brand kits yet. Create one, then select it when a workflow&apos;s
          plan has branding enabled.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {kits.map((kit) => (
            <div
              key={kit.id}
              className="flex items-center gap-3 rounded-xl border p-4"
            >
              {kit.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={kit.logo_url}
                  alt=""
                  className="bg-muted size-12 rounded-lg object-contain"
                />
              ) : (
                <div
                  className="bg-muted size-12 rounded-lg"
                  style={{ backgroundColor: kit.primary_color ?? undefined }}
                />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{kit.name}</p>
                <p className="text-muted-foreground text-xs">
                  {[
                    kit.logo_url && "Logo",
                    kit.watermark_url && "Watermark",
                    kit.default_music_url && "Music",
                    kit.cta_text && "CTA",
                  ]
                    .filter(Boolean)
                    .join(" \u00b7 ") ?? "No assets set"}
                </p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => void onDelete(kit.id)}
                aria-label="Delete brand kit"
              >
                <Trash2 className="text-muted-foreground size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <p className="text-muted-foreground text-xs">
        A brand kit is applied automatically whenever a production plan&apos;s
        branding.brand_kit_id is set \u2014 that still has to be passed through
        a workflow input rather than picked from this page. All fields set below
        (logo, watermark, music, colors, font, caption style, CTA text, voice)
        are applied at render time.
      </p>
    </div>
  );
}

function NewBrandKitDialog({
  onCreated,
}: {
  onCreated: (kit: BrandKit) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [logo, setLogo] = useState<File | null>(null);
  const [watermark, setWatermark] = useState<File | null>(null);
  const [music, setMusic] = useState<File | null>(null);
  const [primaryColor, setPrimaryColor] = useState("");
  const [secondaryColor, setSecondaryColor] = useState("");
  const [fontFamily, setFontFamily] = useState("");
  const [ctaText, setCtaText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { upload, uploading } = useDirectUpload();

  async function onCreate() {
    if (!name.trim()) {
      toast.error("Give the brand kit a name.");
      return;
    }
    setSubmitting(true);
    try {
      const logo_s3_key = logo ? await upload(logo, "brandKitLogo") : undefined;
      const watermark_s3_key = watermark
        ? await upload(watermark, "brandKitWatermark")
        : undefined;
      const default_music_s3_key = music
        ? await upload(music, "brandKitMusic")
        : undefined;
      const kit = await createBrandKit({
        name,
        logo_s3_key,
        watermark_s3_key,
        default_music_s3_key,
        primary_color: primaryColor || undefined,
        secondary_color: secondaryColor || undefined,
        font_family: fontFamily || undefined,
        cta_text: ctaText || undefined,
      });
      onCreated(kit);
      setOpen(false);
      setName("");
      setLogo(null);
      setWatermark(null);
      setMusic(null);
      setPrimaryColor("");
      setSecondaryColor("");
      setFontFamily("");
      setCtaText("");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Couldn't create that brand kit.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || uploading;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          New brand kit
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New brand kit</DialogTitle>
        </DialogHeader>
        <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Brand kit name"
            maxLength={120}
          />
          <FileDropInput
            accept="image/*"
            label="Logo (optional)"
            preview="image"
            onFile={setLogo}
          />
          {/* gap-closure: watermark_s3_key was accepted by the API from
              the start but this form never collected it. Now rendered
              opposite the logo — see render_manifest_builder.py. */}
          <FileDropInput
            accept="image/*"
            label="Watermark (optional, rendered opposite the logo)"
            preview="image"
            onFile={setWatermark}
          />
          <FileDropInput
            accept="audio/*"
            label="Default background music (optional)"
            preview="audio"
            onFile={setMusic}
          />
          <div className="flex gap-2">
            <Input
              value={primaryColor}
              onChange={(e) => setPrimaryColor(e.target.value)}
              placeholder="Primary color, e.g. #FFAA00"
              maxLength={16}
            />
            <Input
              value={secondaryColor}
              onChange={(e) => setSecondaryColor(e.target.value)}
              placeholder="Secondary color"
              maxLength={16}
            />
          </div>
          <Input
            value={fontFamily}
            onChange={(e) => setFontFamily(e.target.value)}
            placeholder="Caption font (optional), e.g. Arial"
            maxLength={120}
          />
          <Input
            value={ctaText}
            onChange={(e) => setCtaText(e.target.value)}
            placeholder="CTA text shown at the end (optional)"
            maxLength={200}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => void onCreate()} disabled={busy}>
            {uploading
              ? "Uploading\u2026"
              : submitting
                ? "Creating\u2026"
                : "Create brand kit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
