import { AuthView } from "@daveyplate/better-auth-ui";
import Image from "next/image";
import Link from "next/link";
import { authViewPaths } from "@daveyplate/better-auth-ui/server";
import { LottieMark } from "~/components/lottie-mark";
import { ThemeToggle } from "~/components/theme-toggle";

export const dynamicParams = false;

export function generateStaticParams() {
  return Object.values(authViewPaths).map((authView) => ({ authView }));
}

export default async function AuthPage({
  params,
}: {
  params: Promise<{ authView: string }>;
}) {
  const { authView } = await params;

  return <main className="vivid-auth-shell">
    <section className="vivid-auth-art">
      <Image src="/images/vivid-creator-studio.jpg" alt="A creator bringing a new idea to life in a warm, colorful studio" fill priority sizes="(max-width: 800px) 100vw, 58vw" />
      <div className="vivid-auth-art-shade" />
      <Link href="/" className="vivid-auth-logo"><span className="vivid-mark">✳</span> vivid<span>gen</span></Link>
      <div className="vivid-auth-art-copy"><span>YOUR STORY, IN MOTION</span><h1>A story in your head.<br/><em>A film on your screen.</em></h1><p>Make room for the idea that’s been waiting to come alive.</p><div className="vivid-auth-ornament"><LottieMark kind="sparkle"/> <i/> ✧ <i/> ✦</div></div>
      <span className="vivid-auth-photo-credit">A LITTLE SPACE FOR BIG IDEAS</span>
    </section>
    <section className="vivid-auth-form"><div className="vivid-auth-theme"><ThemeToggle /></div><Link href="/" className="vivid-auth-logo mobile"><span className="vivid-mark">✳</span> vivid<span>gen</span></Link><div className="vivid-auth-card"><div className="vivid-auth-kicker">{authView === "sign-up" ? "YOUR CREATIVE SPACE" : "WELCOME BACK"}</div><h2>{authView === "sign-up" ? "Let’s make something." : "Good to have you back."}</h2><p>{authView === "sign-up" ? "Your next great story starts with one small step." : "Pick up right where the good ideas left off."}</p><AuthView pathname={authView} /></div><div className="vivid-auth-bottom">MADE FOR PEOPLE WITH SOMETHING TO SAY</div></section>
  </main>;
}
