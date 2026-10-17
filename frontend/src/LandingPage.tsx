import { motion } from 'framer-motion';
import { ArrowRight, Code, Sparkles } from 'lucide-react';

import { Button, buttonVariants } from './components/ui/Button';
import { Card } from './components/ui/Card';
import { Badge } from './components/ui/Badge';
import { ThemeToggle } from './components/ThemeToggle';

const TECH_STACK = [
  { name: 'React', iconUrl: 'https://cdn.simpleicons.org/react/61DAFB' },
  { name: 'Vite', iconUrl: 'https://cdn.simpleicons.org/vite/646CFF' },
  { name: 'TypeScript', iconUrl: 'https://cdn.simpleicons.org/typescript/3178C6' },
  { name: 'Tailwind CSS', iconUrl: 'https://cdn.simpleicons.org/tailwindcss/06B6D4' },
  { name: 'FastAPI', iconUrl: 'https://cdn.simpleicons.org/fastapi/009688' },
  { name: 'Python', iconUrl: 'https://cdn.simpleicons.org/python/3776AB' },
] as const;

const FEATURES = [
  {
    title: 'Generación con IA',
    titleClass: 'text-primary',
    body: 'Subís tu CV maestro y la descripción de la vacante. La IA que configures reescribe la estructura mapeando cada skill y proyecto a los keywords exactos del algoritmo — sin inventar métricas.',
  },
  {
    title: 'Auditoría ATS',
    titleClass: 'text-secondary',
    body: 'Después de generar, obtenés un puntaje de compatibilidad, las palabras clave que faltan, señales de detección de IA y sugerencias accionables para subir el match.',
  },
  {
    title: 'Personalización total',
    titleClass: 'text-warning',
    body: 'Editor YAML en vivo con validación de esquema y autoguardado. Soporta Tech, RR.HH. y Psicología, traducción al inglés y modo claro/oscuro — sin volver a empezar.',
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
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
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
            Adaptá tu CV a cada oferta
            <br />
            en minutos,{' '}
            <span className="bg-primary text-primary-foreground px-3 py-1 inline-block mt-2 transform -rotate-1 rounded-sm">
              no en horas.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-lg md:text-2xl font-medium max-w-2xl text-muted-foreground mt-8 mb-12 leading-relaxed"
          >
            Subí tu CV maestro, pegá la descripción de la vacante y la IA que
            vos configures genera un PDF ATS-friendly listo para enviar. Después
            podés editar el YAML directamente, auditarlo contra el sistema ATS o
            traducirlo al inglés — sin volver a empezar.
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
              Abrir Generador <ArrowRight className="w-6 h-6" aria-hidden="true" />
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
            Construido con
          </h3>
          <div className="marquee-container">
            <div className="marquee-content gap-6">
              {[...TECH_STACK, ...TECH_STACK].map((tech, index) => (
                <Badge
                  key={`${tech.name}-${index}`}
                  variant="default"
                  size="md"
                  className="bg-card flex items-center gap-3 px-6 py-4 cursor-pointer whitespace-nowrap hover:bg-accent"
                  title="Pasá el mouse o enfocá para pausar"
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
            Capacidades
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
              Editado por Johan Ospitia ·
              Código abierto en GitHub.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}