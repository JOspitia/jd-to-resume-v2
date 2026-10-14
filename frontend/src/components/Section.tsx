import type { ReactNode } from 'react';

/**
 * Section — T1 of the UX refactor (specs S2, S3).
 *
 * Reusable wrapper that gives every step in the main flow the same
 * visual treatment: a neo-brutalist card with a numbered tag, a
 * semantic <h2> header, and a slot for an action button on the right.
 *
 * Usage:
 *   <Section number={1} title="PERFIL">
 *     <ProfileSelector ... />
 *   </Section>
 *
 * The number is rendered as a `rm-tag` badge (offset to the top-left like
 * the original layout) and the title is a semantic <h2> so screen readers
 * get a proper document outline.
 */
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
  /** Optional background tone override. Defaults to white. */
  tone?: 'white' | 'muted';
};

const TONE_CLASS: Record<NonNullable<SectionProps['tone']>, string> = {
  white: 'bg-white',
  muted: 'bg-[#F3F4F6]',
};

const TAG_COLOR: Record<number, string> = {
  1: 'bg-purple-600 text-white',
  2: 'bg-orange-500 text-white',
  3: 'bg-blue-700 text-white',
  4: 'bg-gray-800 text-white',
  5: 'bg-emerald-700 text-white',
};

export function Section({
  number,
  title,
  action,
  children,
  bare = false,
  tone = 'white',
}: SectionProps) {
  const tagColor = TAG_COLOR[number] ?? 'bg-black text-white';

  if (bare) {
    return <section className={`rm-box ${TONE_CLASS[tone]} relative`}>{children}</section>;
  }

  return (
    <section
      aria-labelledby={`section-${number}-title`}
      className={`rm-box p-6 md:p-8 ${TONE_CLASS[tone]} relative`}
    >
      <div
        className={`absolute -top-4 -left-4 rm-tag ${tagColor} px-4 py-2 text-lg font-mono font-bold pointer-events-none`}
        aria-hidden="true"
      >
        {number}
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 mt-1">
        <h2
          id={`section-${number}-title`}
          className="text-xl md:text-2xl font-bold font-serif text-black"
        >
          {title}
        </h2>
        {action && <div className="flex items-center gap-2">{action}</div>}
      </div>
      {children}
    </section>
  );
}

export default Section;
