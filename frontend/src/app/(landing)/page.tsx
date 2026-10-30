"use client";

import Link from "next/link";
import { useState } from "react";
import { useTheme } from "next-themes";
import { ArrowDown, ArrowRight, Aperture, Check, Menu, Moon, Play, Sparkles, Sun, X } from "lucide-react";
import { LottieMark } from "~/components/lottie-mark";

const workflows = [
  ["/create/ads", "Ad Studio", "Product + audience → a finished ad"],
  ["/create/youtube", "YouTube", "A topic → long-form video"],
  ["/create/product-video", "Product video", "Bring product details to life"],
  ["/create/url-to-video", "From a URL", "An article → a grounded script"],
  ["/create/podcast", "Podcast video", "Give an episode a visual story"],
  ["/create/presentation", "Presentation", "Narrate and animate a deck"],
  ["/create/shorts", "Shorts", "Find the moments worth cutting"],
  ["/create/dubbing", "Dubbing", "Translate with lip sync"],
  ["/create/text-to-video", "Text to video", "Direct a clip from a written prompt"],
  ["/create/image-to-video", "Image to video", "Bring a still image into motion"],
  ["/create/text-to-image", "Image studio", "Explore a key visual"],
  ["/create/translate", "Video translate", "Localize a video for another audience"],
];

const features = [
  { icon: "01", title: "AI Director", detail: "Turn one idea into a script, storyboard, shot plan, and production you can review before generation.", href: "/create" },
  { icon: "02", title: "Quality routing", detail: "Choose Low, Medium, or High. Vivid selects a capable model using availability, quality, and cost signals.", href: "#models" },
  { icon: "03", title: "Brand Kits", detail: "Keep logos, colors, and audio together, ready to carry your identity into a production.", href: "/brand-kits" },
  { icon: "04", title: "Voice & captions", detail: "Bring narration and captions into the same production flow as your scenes.", href: "/create" },
  { icon: "05", title: "Scene versions", detail: "Try a new direction for a shot while keeping earlier attempts available to compare.", href: "/projects" },
  { icon: "06", title: "Cloud or self-hosted", detail: "Build with Vivid’s hosted capabilities or explore the self-hosted inference path.", href: "#business" },
];

const audiences = [
  ["Marketing & ads", "Build a clear campaign story around a product, audience, and goal."],
  ["Agencies", "Keep client work organized with shared brand systems and production review."],
  ["Creators", "Shape long-form ideas into videos, Shorts, and reusable variations."],
  ["E-commerce", "Show products with the details and imagery that make them yours."],
  ["Education", "Turn presentation material into narrated, visual stories."],
  ["Podcasters", "Give episodes a visual sequence and find moments for Shorts."],
];

const questions = [
  ["Can I review the plan before generation?", "Yes. The Director prepares the script and scene plan for you to review before you approve production."],
  ["Do I have to choose the video model?", "No. Choose a quality level and Vivid routes each scene to an available model suited to the job."],
  ["What is a Brand Kit?", "A reusable collection of visual and audio identity that can be applied across productions."],
  ["Can I try another version of a scene?", "Yes. Scene attempts and versions stay available so you can compare directions and return to an earlier one."],
  ["Where can I see credit costs?", "The current workspace shows the active plan, credit balance, and top-up options in Credits."],
  ["Where do I find my work?", "Projects collect storyboard productions. Generations keeps finished and in-progress media easy to revisit."],
];

const bundles = [
  { number: "01", name: "Creator", label: "For your next big idea", detail: "A guided shot plan with space to shape every scene.", points: ["AI Director planning", "Scene-by-scene control", "Quality routing"], href: "/create" },
  { number: "02", name: "Studio", label: "For a team in motion", detail: "A shared creative system for people making work together.", points: ["Shared Brand Kits", "Pooled team credits", "Review-ready versions"], href: "/brand-kits", featured: true },
  { number: "03", name: "Agency", label: "For many stories at once", detail: "A production foundation for consistent client work.", points: ["Multiple Brand Kits", "API & webhooks", "Scalable workflows"], href: "/create" },
];

function ThemeButton() {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme !== "light";
  return <button type="button" className="vivid-theme-button" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} onClick={() => setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>;
}

function Kicker({ children, light = false }: { children: React.ReactNode; light?: boolean }) {
  return <div className={`vivid-eyebrow${light ? " dark" : ""}`}><span />{children}</div>;
}

export default function LandingPage() {
  const [workflow, setWorkflow] = useState("Product launch");
  const [menuOpen, setMenuOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const prompts: Record<string, string> = {
    "Product launch": "A new ritual for slow mornings. Warm light, tactile details, a little wonder.",
    "Creator story": "A maker finding their rhythm. Honest moments, a bright studio, a story worth sharing.",
    "Campaign film": "A summer drop made to stop the scroll. Bold color, joyful movement, one clear idea.",
  };
  const samplePrompt = prompts[workflow] ?? prompts["Product launch"]!;
  const scene = workflow === "Product launch" ? "Soft light, first sip" : workflow === "Creator story" ? "A maker finds her rhythm" : "Color, movement, impact";
  const createHref = `/create?prompt=${encodeURIComponent(prompt.trim() || samplePrompt)}`;
  const nav = [["#features", "Platform"], ["#workflows", "Workflows"], ["#industry", "Industry"], ["#business", "Business"], ["#resources", "Resources"], ["#pricing", "Pricing"], ["#faq", "FAQ"]];
  const closeMenu = () => setMenuOpen(false);

  return <main className="vivid-site">
    <header className="vivid-nav">
      <Link href="/" className="vivid-wordmark"><span className="vivid-mark"><Aperture size={17}/></span> vivid<span>gen</span></Link>
      <nav className="vivid-nav-links" aria-label="Main navigation">{nav.map(([href, label]) => <a key={href} href={href}>{label}</a>)}</nav>
      <div className="vivid-nav-actions"><ThemeButton/><Link href="/auth/sign-in" className="vivid-login">Sign in</Link><Link href="/create" className="vivid-nav-cta">Start creating <ArrowRight size={15}/></Link></div>
      <button className="vivid-menu-toggle" aria-label={menuOpen ? "Close menu" : "Open menu"} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X/> : <Menu/>}</button>
      {menuOpen && <nav className="vivid-mobile-panel" aria-label="Mobile navigation">{nav.map(([href, label]) => <a key={href} href={href} onClick={closeMenu}>{label}</a>)}<div><ThemeButton/><Link href="/auth/sign-in" onClick={closeMenu}>Sign in</Link><Link href="/create" className="vivid-nav-cta" onClick={closeMenu}>Start creating <ArrowRight size={15}/></Link></div></nav>}
    </header>

    <section className="vivid-hero" id="try"><div className="vivid-hero-image"/><div className="vivid-hero-shade"/><div className="vivid-hero-copy"><Kicker>THE AI VIDEO STUDIO</Kicker><h1>Your next<br/>great story<br/><em>starts here.</em></h1><p>From the first spark to the final frame, make the kind of video that feels unmistakably yours.</p><div className="vivid-hero-actions"><Link href={createHref} className="vivid-primary">Start creating <ArrowRight size={17}/></Link><a href="#how" className="vivid-secondary"><span className="vivid-play">↘</span> See how it works</a></div><div className="vivid-hero-note"><LottieMark kind="sparkle"/> Plan it. Review it. Make it yours.</div></div>
      <div className="vivid-brief-card"><div className="vivid-brief-head"><span><i/> DIRECTOR PREVIEW</span><LottieMark kind="camera"/></div><div className="vivid-workflow-tabs" role="group" aria-label="Choose a sample video workflow">{Object.keys(prompts).map((item) => <button key={item} onClick={() => setWorkflow(item)} className={item===workflow?"active":""} aria-pressed={item===workflow}>{item}</button>)}</div><p className="vivid-prompt" aria-live="polite">“{samplePrompt}”</p><div className="vivid-brief-foot"><span>01 / {workflow.toUpperCase()} PREVIEW</span><span className="vivid-scene-dots"><i/><i/><i/><i/></span></div><div className="vivid-frame-preview"><div className="vivid-frame-image"/><div className="vivid-frame-label"><span>SCENE 01</span><b>{scene}</b></div><span className="vivid-frame-play">▶</span></div><span className="vivid-float-tag"><Sparkles size={12}/> Directed by your idea</span></div><a className="vivid-scroll-cue" href="#features"><ArrowDown size={14}/> SCROLL TO EXPLORE</a>
    </section>

    <section className="vivid-proof-strip"><span>ONE CREATIVE STUDIO</span><i/><span>12 WAYS INTO VIDEO</span><i/><span>ONE REVIEWABLE PRODUCTION</span><i/><span>YOUR CALL AT EVERY STEP</span></section>

    <section className="vivid-content-section vivid-platform" id="features"><div className="vivid-page-wrap"><div className="vivid-section-heading"><div><Kicker>PLATFORM</Kicker><h2>Everything a production needs,<br/><em>already in the room.</em></h2></div><p>Vivid brings direction, generation, brand assets, scene versions, and delivery into one creative flow.</p></div><div className="vivid-feature-grid">{features.map((feature)=><Link href={feature.href} className="vivid-feature-card" key={feature.title}><span>{feature.icon}</span><h3>{feature.title}</h3><p>{feature.detail}</p><b>Explore <ArrowRight size={14}/></b></Link>)}</div></div></section>

    <section className="vivid-content-section vivid-how" id="how"><div className="vivid-page-wrap"><div className="vivid-section-heading centered"><Kicker light>HOW IT WORKS</Kicker><h2>Three steps.<br/><em>No mystery in the middle.</em></h2><p>See the plan first. Generation starts when you approve it.</p></div><div className="vivid-how-grid"><article><span>01 / DESCRIBE</span><div className="vivid-how-visual"><Sparkles/><b>One sentence is enough.</b><small>A story, a product, a direction.</small></div><h3>Bring the first spark.</h3><p>Start with what you want to make. Add tone, audience, or length when they help.</p></article><article><span>02 / REVIEW</span><div className="vivid-how-visual"><div className="vivid-mini-plan"><i/><i/><i/></div><b>Every scene, in view.</b><small>Adjust the direction before production.</small></div><h3>Shape the plan.</h3><p>Review your script, shot plan, and scenes before you commit credits to generation.</p></article><article><span>03 / MAKE</span><div className="vivid-how-visual vivid-how-photo"><Play fill="currentColor"/></div><h3>Make it yours.</h3><p>Generate and refine scenes, bring in voice and captions, and assemble the finished story.</p></article></div></div></section>

    <section className="vivid-studio" id="studio"><div className="vivid-studio-photo"><div className="vivid-photo-caption"><span>THE VIVID STUDIO</span><b>Make room for the<br/>work you imagined.</b></div></div><div className="vivid-studio-copy"><Kicker light>A CREATIVE PARTNER, NOT ANOTHER TOOL</Kicker><h2>Big-screen feeling.<br/><em>Small-step process.</em></h2><p>Bring the rough idea. Vivid helps you shape it into a story, plan the shots, and make every frame count.</p><div className="vivid-steps"><div><span>01</span><b>Find the feeling</b><small>Start with a thought, a link, or a product.</small></div><div><span>02</span><b>Shape the story</b><small>See your script and scenes before production.</small></div><div><span>03</span><b>Make it yours</b><small>Generate, refine, and bring the film together.</small></div></div><Link href="/create" className="vivid-text-link">Explore the studio <ArrowRight size={16}/></Link></div></section>

    <section className="vivid-content-section vivid-workflows" id="workflows"><div className="vivid-page-wrap"><div className="vivid-section-heading"><div><Kicker>WORKFLOWS</Kicker><h2>Start with the video<br/><em>you’re here to make.</em></h2></div><p>Begin with a brief, a product, a URL, an episode, a presentation, or footage you already have.</p></div><div className="vivid-workflow-grid">{workflows.map(([href,label,detail],index)=><Link href={href!} key={href} className="vivid-workflow-card"><span>{String(index+1).padStart(2,"0")}</span><div><h3>{label}</h3><p>{detail}</p></div><ArrowRight size={16}/></Link>)}</div><Link href="/create" className="vivid-text-link">See every workflow <ArrowRight size={15}/></Link></div></section>

    <section className="vivid-content-section vivid-showcase"><div className="vivid-page-wrap"><div className="vivid-section-heading"><div><Kicker>PRODUCTION, NOT PLACEHOLDERS</Kicker><h2>From the first frame<br/><em>to the final cut.</em></h2></div><p>Direction, visual generation, editing decisions, brand consistency, and delivery belong in the same story.</p></div><div className="vivid-showcase-grid"><Link href="/create" className="vivid-showcase-tile wide"><div className="vivid-showcase-image shot"/><span>01 / CAPTURE</span><b>Generate shots with a production brief.</b><ArrowRight size={15}/></Link><Link href="/projects" className="vivid-showcase-tile"><div className="vivid-showcase-image edit"/><span>02 / DIRECT</span><b>Review scenes, versions, and the edit.</b><ArrowRight size={15}/></Link><Link href="/generations" className="vivid-showcase-tile"><div className="vivid-showcase-image deliver"/><span>03 / DELIVER</span><b>Keep each generation ready for the next cut.</b><ArrowRight size={15}/></Link></div></div></section>

    <section className="vivid-content-section vivid-routing" id="models"><div className="vivid-page-wrap vivid-routing-layout"><div className="vivid-routing-image"><div><span>MODEL ORCHESTRATION</span><b>One quality choice.<br/>Many capable models.</b></div></div><div><Kicker>QUALITY ROUTING</Kicker><h2>You never have to<br/><em>pick the model.</em></h2><p>Choose the outcome you care about. Vivid evaluates capability, provider health, cost, and availability for each scene.</p><div className="vivid-quality-list">{[["Low","Fast & economical","Economy or self-hosted paths where available"],["Medium","Balanced quality","Standard models with sensible fallback"],["High","Highest quality","Premium models when the shot needs them"]].map(([level,title,copy])=><div key={level}><b>{level}</b><span><strong>{title}</strong><small>{copy}</small></span><ArrowRight size={14}/></div>)}</div><Link href="/create" className="vivid-text-link">Create with quality levels <ArrowRight size={15}/></Link></div></div></section>

    <section className="vivid-content-section vivid-industry" id="industry"><div className="vivid-page-wrap"><div className="vivid-section-heading"><div><Kicker>INDUSTRY</Kicker><h2>Whatever the story,<br/><em>there’s a way in.</em></h2></div><p>Video workflows for the work you do and the people you want to reach.</p></div><div className="vivid-industry-grid">{audiences.map(([title,detail])=><Link href="/create" key={title} className="vivid-industry-card"><h3>{title}</h3><p>{detail}</p><ArrowRight size={15}/></Link>)}</div></div></section>

    <section className="vivid-content-section vivid-business" id="business"><div className="vivid-page-wrap vivid-business-panel"><div className="vivid-business-intro"><Kicker light>BUSINESS & TEAMS</Kicker><h2>Built to run across<br/><em>a whole team.</em></h2><p>Shared brand systems, pooled credits, and developer access make Vivid useful beyond one creator.</p></div><div className="vivid-business-grid"><Link href="/brand-kits"><span>BRAND, ONCE</span><h3>Shared Brand Kits</h3><p>Keep logos, colors, and audio consistent across productions.</p><ArrowRight size={15}/></Link><Link href="/credits"><span>CREDITS, POOLED</span><h3>Team credit pools</h3><p>Give a team a shared balance for collaborative production.</p><ArrowRight size={15}/></Link><Link href="/create"><span>FOR DEVELOPERS</span><h3>API & webhooks</h3><p>Connect planning and generation to the systems you use.</p><ArrowRight size={15}/></Link></div></div></section>

    <section className="vivid-content-section vivid-bundles" id="pricing"><div className="vivid-page-wrap"><div className="vivid-bundle-head"><div><Kicker>POPULAR SERVICE BUNDLES</Kicker><h2>Choose your <em>creative pace.</em></h2></div><p>Distinct ways to start for creators, teams, and agencies. Credit rates and top-ups stay visible in your workspace.</p></div><div className="vivid-bundle-grid">{bundles.map(bundle=><article key={bundle.name} className={`vivid-bundle-card ${bundle.featured?"featured":""}`}><div className="vivid-bundle-top"><span>{bundle.number} / 03</span>{bundle.featured&&<span className="vivid-featured-tag"><Sparkles size={12}/> POPULAR</span>}</div><h3>{bundle.name}</h3><b className="vivid-bundle-label">{bundle.label}</b><p>{bundle.detail}</p><ul>{bundle.points.map(point=><li key={point}><Check size={14}/>{point}</li>)}</ul><Link href={bundle.href} className="vivid-bundle-link">Explore {bundle.name} <ArrowRight size={15}/></Link></article>)}</div><div className="vivid-pricing-note"><span>See your current plan, credit balance, and top-up options.</span><Link href="/credits">View pricing & credits <ArrowRight size={14}/></Link></div></div></section>

    <section className="vivid-content-section vivid-resources" id="resources"><div className="vivid-page-wrap"><div className="vivid-section-heading"><div><Kicker>RESOURCES</Kicker><h2>Learn the system.<br/><em>Then build faster.</em></h2></div><p>Find your footing with the product paths that are ready today.</p></div><div className="vivid-resource-grid">{[["01","Product guide","Explore the Director, workflows, and production stages.","/create"],["02","API & integrations","Connect planning and production to your workflow.","/create"],["03","Brand Kits","Set up reusable visual and audio identity.","/brand-kits"],["04","Help & answers","Find quick answers below.","#faq"]].map(([number,title,copy,href])=><Link href={href!} key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p><ArrowRight size={15}/></Link>)}</div></div></section>

    <section className="vivid-content-section vivid-faq" id="faq"><div className="vivid-page-wrap vivid-faq-layout"><div><Kicker light>FAQ</Kicker><h2>Good questions.<br/><em>Clear answers.</em></h2><p>A few things worth knowing before your first production.</p></div><div className="vivid-faq-list">{questions.map(([question,answer])=><details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}</div></div></section>

    <section className="vivid-end" id="final-cta"><div className="vivid-end-orb"><Sparkles size={20}/></div><Kicker>YOUR NEXT SCENE IS WAITING</Kicker><h2>Make something<br/><em>only you could make.</em></h2><p>Bring us the idea you can’t stop thinking about.</p><form className="vivid-end-form" onSubmit={(event)=>{event.preventDefault();window.location.assign(createHref);}}><input value={prompt} onChange={(event)=>setPrompt(event.target.value)} placeholder="A story I want to bring to life…" aria-label="Describe a video idea"/><button className="vivid-primary" type="submit">Start creating <ArrowRight size={16}/></button></form></section>

    <section className="vivid-legal" id="legal"><span>TERMS & PRIVACY</span><p>Use Vivid Gen lawfully and respect others’ rights. Your data, credits, and generated media are handled under the service and provider terms that apply to your account.</p><Link href="/auth/sign-up">Create an account <ArrowRight size={14}/></Link></section>
    <footer className="vivid-footer"><div><Link href="/" className="vivid-wordmark"><span className="vivid-mark"><Aperture size={17}/></span> vivid<span>gen</span></Link><small>THE AI DIRECTOR FOR VIDEO</small></div><div>{nav.map(([href,label])=><a href={href} key={href}>{label}</a>)}</div><div><Link href="/auth/sign-in">Sign in</Link><Link href="/create">Start creating</Link><ThemeButton/></div></footer>
  </main>;
}
