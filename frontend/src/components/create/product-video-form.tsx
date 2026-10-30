"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createProductVideoWorkflow } from "~/actions/workflows";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";

export function ProductVideoForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [features, setFeatures] = useState<string[]>([]);
  const [featureInput, setFeatureInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function addFeature() {
    if (featureInput.trim()) {
      setFeatures((prev) => [...prev, featureInput.trim()]);
      setFeatureInput("");
    }
  }

  async function onSubmit() {
    if (!name.trim() || !description.trim()) {
      toast.error("Product name and description are required.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createProductVideoWorkflow({ product_name: name, product_description: description, features });
      router.push(`/projects/${result.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't plan this video.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Product name" maxLength={200} />
      <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Product description" rows={3} maxLength={3000} />
      <div>
        <p className="mb-2 text-xs font-medium">Features (optional)</p>
        <div className="flex gap-2">
          <Input
            value={featureInput}
            onChange={(e) => setFeatureInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addFeature())}
            placeholder="e.g. Waterproof up to 50m"
          />
          <Button type="button" variant="outline" size="icon" onClick={addFeature}>
            <Plus className="size-4" />
          </Button>
        </div>
        {features.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {features.map((f, i) => (
              <span key={i} className="bg-muted flex items-center gap-1 rounded-full px-3 py-1 text-xs">
                {f}
                <button onClick={() => setFeatures((prev) => prev.filter((_, j) => j !== i))}>
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void onSubmit()} disabled={submitting}>
          {submitting ? "Planning\u2026" : "Plan my video"}
        </Button>
      </div>
    </div>
  );
}
