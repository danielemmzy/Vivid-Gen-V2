import { ProductVideoForm } from "~/components/create/product-video-form";

export default function ProductVideoPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Product Video</h1>
        <p className="text-muted-foreground mt-1 text-sm">Showcase a product using only the real facts you give it.</p>
      </div>
      <ProductVideoForm />
    </div>
  );
}
