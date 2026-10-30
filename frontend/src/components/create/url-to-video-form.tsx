"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  createUrlToVideoWorkflow,
  previewUrlToVideoArticle,
  type UrlArticlePreview,
} from "~/actions/workflows";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";

export function UrlToVideoForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<UrlArticlePreview | null>(null);
  const [articleText, setArticleText] = useState("");
  const [reading, setReading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function readArticle() {
    if (!url.trim()) {
      toast.error("Paste an article URL first.");
      return;
    }
    setReading(true);
    try {
      const result = await previewUrlToVideoArticle({ url: url.trim() });
      setPreview(result);
      setArticleText(result.article_text);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Couldn't read that article. Try another public URL.",
      );
    } finally {
      setReading(false);
    }
  }

  async function onSubmit() {
    if (!url.trim()) {
      toast.error("Paste an article URL first.");
      return;
    }
    if (!articleText.trim()) {
      toast.error("Review or add the article text before creating a plan.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createUrlToVideoWorkflow({
        url: url.trim(),
        duration_seconds: 60,
        article_text: articleText.trim(),
      });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Couldn't fetch or plan from that URL.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setPreview(null);
          }}
          placeholder="https://example.com/article"
        />
        <Button
          variant="secondary"
          onClick={() => void readArticle()}
          disabled={reading}
        >
          {reading ? "Reading article…" : "Read URL"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Vivid respects robots.txt. Read the source first, edit it into the story
        you want, then create an editable video plan.
      </p>
      {preview && (
        <section className="bg-muted/30 space-y-3 rounded-lg border p-4">
          <div className="space-y-1">
            <h3 className="font-medium">Review your source</h3>
            {preview.title && <p className="text-sm">{preview.title}</p>}
            {preview.description && (
              <p className="text-muted-foreground text-xs">
                {preview.description}
              </p>
            )}
            <p className="text-muted-foreground text-xs">
              {preview.word_count.toLocaleString()} words extracted ·{" "}
              {preview.visual_candidates} usable image candidate
              {preview.visual_candidates === 1 ? "" : "s"}
            </p>
          </div>
          <Textarea
            value={articleText}
            onChange={(e) => setArticleText(e.target.value)}
            rows={12}
            maxLength={15000}
            aria-label="Extracted article text"
          />
          <p className="text-muted-foreground text-xs">
            Remove tangents, add missing context, or rewrite the source before
            Vivid turns it into scenes. Public image references are imported
            only after you create the plan.
          </p>
        </section>
      )}
      <div className="flex justify-end border-t pt-4">
        <Button
          onClick={() => void onSubmit()}
          disabled={submitting || !preview}
        >
          {submitting ? "Creating plan…" : "Create editable plan"}
        </Button>
      </div>
    </div>
  );
}
