import { motion } from 'framer-motion';
import { Code2, Briefcase, Brain } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { DomainGame } from '../hooks/useProfile';

/**
 * ProfileSelector — T5 of the UX refactor (spec S7).
 *
 * The domain profile is the main differentiator of the product, so it stays
 * the most prominent element of the page: full width, own card, own accent
 * tag, one card per domain with an icon and a one-line description.
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
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="rm-box p-6 md:p-7 flex flex-col bg-white relative"
    >
      <div className="absolute -top-4 -left-4 rm-tag bg-purple-600 text-white px-4 py-2 text-lg">PROFILE</div>
      <h2 className="text-2xl font-bold mb-3 font-serif mt-2">Select Profile</h2>
      <p className="text-sm text-gray-600 mb-5 font-mono">
        Choose the profile of the CV you are tailoring. The prompt, skill taxonomy and section labels adapt to the domain.
      </p>
      <div className="grid sm:grid-cols-3 gap-4">
        {PROFILE_OPTIONS.map(({ id, Icon, label, description }) => {
          const selected = domainGame === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              aria-pressed={selected}
              className={`rm-btn p-4 flex flex-col items-start text-left gap-2 ${selected ? 'bg-blue-700 text-white' : 'bg-white text-black'}`}
            >
              <div className="flex items-center gap-2 w-full">
                <Icon className="w-5 h-5 shrink-0" />
                <span className="font-bold font-mono text-base uppercase tracking-wide">{label}</span>
              </div>
              <p className={`text-xs leading-snug ${selected ? 'text-blue-100' : 'text-gray-600'}`}>{description}</p>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}

export default ProfileSelector;