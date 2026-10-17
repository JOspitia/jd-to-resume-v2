import type { ReactNode } from 'react';

import { Card } from './ui/Card';
import { Badge, badgeVariants } from './ui/Badge';

/**
 * Section — T1 of the UX refactor (specs S2, S3).
 *
 * Reusable wrapper that gives every step in the main flow the same
 * visual treatment: a neo-brutalist card with a numbered tag, a
 * semantic <h2> header, and a slot for an action button on the right.
 *
 * PR5 polish: now uses the <Card> and <Badge> primitives from PR2
 * instead of raw .rm-box / .rm-tag classes. Tag colors map to the
 * Badge variant tokens (`primary`/`secondary`/`info`/`success`/etc.)
 * so dark mode re-tints them via tokens without touching this file.
 *
 * Usage:
 *   <Section number={1} title="PERFIL">
 *     <ProfileSelector ... />
 *   </Section>
 */
export type SectionTone = 'default' | 'muted';

export type SectionProps = {
  number: number;
  title: string;
  /** Optional element rendered on the right side of the header (e.g. a
   *  "Reset" button). Kept generic so any section can host it. */
  action?: ReactNode;
  /** Children rendered inside the card body. */
  children: ReactNode;
  /** When true, removes the outer padding and offset so the section can
   *  be embedded in a container that already provides its own card. */
  bare?: boolean;
  /** Optional background tone override. */
  tone?: SectionTone;
};

/** Map section number → Badge variant. Each section gets a unique color
 *  so the user can pattern-match the numbered tag to the step in their
 *  head. */
const TAG_VARIANT: Record<number, Parameters<typeof badgeVariants>[0]['variant']> = {
  1: 'primary',
  2: 'secondary',
  3: 'info',
  4: 'default',
  5: 'success',
};

const TONE_CLASS: Record<SectionTone, string> = {
  default: '',
  muted: 'bg-muted',
};

export function Section({
  number,
  title,
  action,
  children,
  bare = false,
  tone = 'default',
}: SectionProps) {
  const tagVariant = TAG_VARIANT[number] ?? 'default';

  if (bare) {
    return (
      <Card variant="default" className={`${TONE_CLASS[tone]} relative`}>
        {children}
      </Card>
    );
  }

  return (
    <Card
      variant="default"
      size="lg"
      aria-labelledby={`section-${number}-title`}
      className={`${TONE_CLASS[tone]} relative`}
    >
      <div
        className="absolute -top-4 -left-4 pointer-events-none"
        aria-hidden="true"
      >
        <Badge variant={tagVariant} size="md" className="px-4 py-2 text-lg font-bold">
          {number}
        </Badge>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 mt-1">
        <h2
          id={`section-${number}-title`}
          className="text-xl md:text-2xl font-bold font-serif text-foreground"
        >
          {title}
        </h2>
        {action && <div className="flex items-center gap-2">{action}</div>}
      </div>
      {children}
    </Card>
  );
}

export default Section;