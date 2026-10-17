import { motion } from 'framer-motion';
import { ArrowRight, Code, Sparkles } from 'lucide-react';

import { Button, buttonVariants } from './components/ui/Button';
import { Card } from './components/ui/Card';
import { Badge } from './components/ui/Badge';

const TECH_STACK = [
  { name: 'React', iconUrl: 'https://cdn.simpleicons.org/react/61DAFB' },
  { name: 'Vite', iconUrl: 'https://cdn.simpleicons.org/vite/646CFF' },
  { name: 'TypeScript', iconUrl: 'https://cdn.simpleicons.org/typescript/3178C6' },
  { name: 'Tailwind CSS', iconUrl: 'https://cdn.simpleicons.org/tailwindcss/06B6D4' },
  { name: 'FastAPI', iconUrl: 'https://cdn.simpleicons.org/fastapi/009688' },
  { name: 'Google Gemini', iconUrl: 'https://cdn.simpleicons.org/googlegemini/8E75B2' },
  { name: 'Python', iconUrl: 'https://cdn.simpleicons.org/python/3776AB' },
] as const;

const FEATURES = [
  {
    title: 'AI Analysis',
    titleClass: 'text-primary',
    body: 'Uses Google Gemini to perfectly map your existing skills and projects to the exact keywords algorithms are hunting for.',
  },
  {
    title: 'Auto Formatting',
    titleClass: 'text-secondary',
    body: 'Generates a flawless, strictly 1-page PDF layout combining classic ATS-friendly structure using purely headless Playwright.',
  },
  {
    title: 'Knowledge Base',
    titleClass: 'text-pink-600',
    body: 'Can hook into a personal databank of expanded experiences to smartly swap out projects that fit the job better.',
  },
] as const;

export default function LandingPage({ onStart }: { onStart: () => void }) {
  return (
    <div className="min-h-screen text-foreground flex flex-col items-center pb-24 selection:bg-primary selection:text-primary-foreground">
      {/* Custom marquee keyframes. Paused on hover via CSS so keyboard
          users can pause too (hover-only would leave screen reader users
          stuck hearing motion). */}
      <style>{`
        @keyframes scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .marquee-container {
          overflow: hidden;
          width: 100%;
          padding: 1rem 0;
          mask-image: linear-gradient(to right, transparent, black 10%, black 90%, transparent);
          -webkit-mask-image: linear-gradient(to right, transparent, black 10%, black 90%, transparent);
        }
        .marquee-content {
          display: flex;
          width: max-content;
          animation: scroll 40s linear infinite;
        }
        .marquee-content:hover,
        .marquee-content:focus-within {
          animation-play-state: paused;
        }
        @media (prefers-reduced-motion: reduce) {
          .marquee-content {
            animation: none;
          }
        }
      `}</style>

      {/* Navbar */}
      <nav
        className="w-full max-w-7xl mx-auto px-6 md:px-12 py-6 flex justify-between items-center z-20"
        aria-label="Navegación principal"
      >
        <div
          className="rm-box px-4 py-2 font-black text-xl bg-card flex items-center gap-2"
          style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}
        >
          <Sparkles className="w-5 h-5 text-primary" aria-hidden="true" />
          ResumeTailor-AI
        </div>

        <a
          href="https://github.com/VJsharan/jd-to-resume-pdf"
          target="_blank"
          rel="noreferrer"
          aria-label="Ver el repositorio en GitHub"
          className={buttonVariants({ variant: 'primary', size: 'md' })}
        >
          <Code className="w-5 h-5" aria-hidden="true" /> GitHub
        </a>
      </nav>

      <div className="w-full max-w-7xl mx-auto px-6 md:px-12 flex flex-col items-center mt-12 md:mt-24 space-y-24">
        {/* HERO SECTION */}
        <section
          className="flex flex-col items-center text-center w-full"
          aria-labelledby="hero-title"
        >
          <motion.h1
            id="hero-title"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-5xl md:text-7xl font-black font-serif leading-[1.05] tracking-tighter max-w-4xl"
          >
            Instantly tailor your
            <br />
            resume to{' '}
            <span className="bg-primary text-primary-foreground px-3 py-1 inline-block mt-2 transform -rotate-1 rounded-sm">
              any job description.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-lg md:text-2xl font-medium max-w-2xl text-muted-foreground mt-8 mb-12 leading-relaxed"
          >
            Upload your master resume PDF, paste the job description, and let
            our AI perfectly format and optimize a new ATS-friendly PDF in
            seconds.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Button
              onClick={onStart}
              variant="secondary"
              size="lg"
              className="px-10 py-5 text-xl"
            >
              Open Generator <ArrowRight className="w-6 h-6" aria-hidden="true" />
            </Button>
          </motion.div>
        </section>

        {/* TECH STACK SECTION (Scrolling Marquee) */}
        <section
          className="w-full text-center flex flex-col items-center"
          aria-labelledby="tech-stack-title"
        >
          <h3
            id="tech-stack-title"
            className="font-mono text-xs tracking-widest text-muted-foreground uppercase font-bold mb-4"
          >
            Built With
          </h3>
          <div className="marquee-container">
            <div className="marquee-content gap-6">
              {[...TECH_STACK, ...TECH_STACK].map((tech, index) => (
                <Badge
                  key={`${tech.name}-${index}`}
                  variant="default"
                  size="md"
                  className="bg-card flex items-center gap-3 px-6 py-4 cursor-pointer whitespace-nowrap hover:bg-accent"
                  title="Hover or focus to pause"
                >
                  <img
                    src={tech.iconUrl}
                    alt=""
                    aria-hidden="true"
                    className="w-6 h-6 object-contain drop-shadow-sm"
                  />
                  <span className="font-bold text-base">{tech.name}</span>
                </Badge>
              ))}
            </div>
          </div>
        </section>

        {/* FEATURES GRID */}
        <section
          className="w-full text-center space-y-10"
          aria-labelledby="features-title"
        >
          <h2
            id="features-title"
            className="text-4xl font-serif font-black tracking-tight"
          >
            Features
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
            {FEATURES.map((feature) => (
              <Card
                key={feature.title}
                variant="default"
                size="lg"
                className="text-left space-y-4 hover:-translate-y-1"
              >
                <h3
                  className={`text-2xl font-serif font-bold ${feature.titleClass}`}
                >
                  {feature.title}
                </h3>
                <p className="font-medium text-muted-foreground leading-relaxed">
                  {feature.body}
                </p>
              </Card>
            ))}
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer
        className="w-full border-t-2 border-border bg-card mt-32"
        aria-label="Pie de página"
      >
        <div className="w-full max-w-7xl mx-auto p-8 md:p-12">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6 md:gap-8">
            <div
              className="rm-box px-4 py-2 font-black text-lg flex items-center bg-card border-2 border-border"
              style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}
            >
              <Sparkles className="w-4 h-4 text-primary inline mr-2" aria-hidden="true" />
              ResumeTailor-AI
            </div>
            <div className="font-mono text-xs md:text-sm text-muted-foreground font-medium text-center md:text-right">
              © {new Date().getFullYear()} Resume Tailor AI ·
              Edited by Johan Ospitia ·
              Open source on GitHub.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}