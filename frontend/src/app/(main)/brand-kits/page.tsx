import { listBrandKits } from "~/actions/brand-kits";
import { BrandKitsList } from "~/components/brand-kits-list";

export default async function BrandKitsPage() {
  const { brand_kits } = await listBrandKits();
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="font-display text-3xl font-semibold">Brand Kits</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Logo and background music applied automatically when a production plan has branding enabled.
        </p>
      </div>
      <BrandKitsList brandKits={brand_kits} />
    </div>
  );
}
