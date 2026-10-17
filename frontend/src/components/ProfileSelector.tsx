import { motion } from 'framer-motion';
import { Code2, Briefcase, Brain, type LucideIcon } from 'lucide-react';
import type { DomainGame } from '../hooks/useProfile';

/**
 * ProfileSelector — T6 of the UX refactor (spec S10).
 *
 * Three large tiles, one per domain. The selected tile is filled with the
 * brand color and inverted text. The icons are 28px (bigger than before)
 * and the description sits right under the label so each tile is
 * self-explanatory in a single glance.
 *
 * Wrapped by <Section number={1} title="PERFIL"> in ToolApp, so this
 * component no longer renders its own `rm-tag` or heading.
 */

type ProfileOption = {
  id: DomainGame;
  Icon: LucideIcon;
  label: string;
  description: string;
};

const PROFILE_OPTIONS: ProfileOption[] = [
  {
    id: 'tech',
    Icon: Code2,
    label: 'Tecnología',
    description: 'Ingenieros de software, full-stack, data/ML, DevOps, QA.',
  },
  {
    id: 'hr_recruiting',
    Icon: Briefcase,
    label: 'Analistas de Contratación',
    description: 'Reclutadores, selección, HRBP, employer branding, onboarding.',
  },
  {
    id: 'psychology',
    Icon: Brain,
    label: 'Psicología',
    description: 'Psicólogos/as organizacional, clínico, educativo, social o forense.',
  },
];

export type ProfileSelectorProps = {
  domainGame: DomainGame;
  onChange: (game: DomainGame) => void;
};

export function ProfileSelector({ domainGame, onChange }: ProfileSelectorProps) {
  return (
    <div className="grid sm:grid-cols-3 gap-4" role="radiogroup" aria-label="Dominio profesional">
      {PROFILE_OPTIONS.map(({ id, Icon, label, description }) => {
        const selected = domainGame === id;
        return (
          <motion.button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(id)}
            whileHover={{ y: -2 }}
            whileTap={{ y: 0 }}
            className={`p-5 text-left border-2 flex flex-col gap-2 transition-all ${
              selected
                ? 'border-primary bg-primary text-primary-foreground shadow-neo'
                : 'border-border bg-card text-foreground shadow-neo-sm hover:bg-accent'
            }`}
          >
            <div className="flex items-center gap-2 w-full">
              <Icon className="w-7 h-7 shrink-0" strokeWidth={1.75} />
              <span className="font-bold font-mono text-sm md:text-base uppercase tracking-wide">
                {label}
              </span>
            </div>
            <p
              className={`text-xs leading-snug ${
                selected ? 'text-primary-foreground/80' : 'text-muted-foreground'
              }`}
            >
              {description}
            </p>
          </motion.button>
        );
      })}
    </div>
  );
}

export default ProfileSelector;
