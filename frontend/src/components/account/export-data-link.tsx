import Link from "next/link";

export function ExportDataLink() {
  return (
    <Link
      href="/api/account/export"
      className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-4"
    >
      Download your account data
    </Link>
  );
}
