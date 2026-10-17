/**
 * Card — primitive container built on the brutalist design system.
 *
 * Variants control the surface (background) and elevation (shadow).
 * The brutalist aesthetic keeps hard borders + offset shadows on every
 * variant; the only differences are the background color.
 *
 * Variants:
 *   - default  → card surface, neo shadow (standard surface)
 *   - elevated → card surface, neo-lg shadow (hovered/active state)
 *   - muted    → muted surface, neo shadow (secondary info)
 *   - accent   → accent surface, neo shadow (highlighted info)
 *   - success  → success/10 tint, standard shadow (positive result)
 *   - warning  → warning/10 tint, standard shadow (attention needed)
 *   - info     → info/10 tint, standard shadow (informational)
 *   - danger   → destructive/10 tint, standard shadow (error)
 *
 * Sizes: sm (p-4), md (p-6), lg (p-8), xl (p-10).
 */

import * as React from 'react';
import { cn } from '../../lib/utils';

export type CardVariant =
  | 'default'
  | 'elevated'
  | 'muted'
  | 'accent'
  | 'success'
  | 'warning'
  | 'info'
  | 'danger';

export type CardSize = 'sm' | 'md' | 'lg' | 'xl';

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  size?: CardSize;
  /** Disable hover translate effect for non-interactive cards. */
  static?: boolean;
}

export const cardVariants = ({
  variant = 'default',
  size = 'md',
  static: isStatic = false,
}: {
  variant?: CardVariant;
  size?: CardSize;
  static?: boolean;
}): string => {
  const sizeClasses: Record<CardSize, string> = {
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
    xl: 'p-10',
  };

  const variantClasses: Record<CardVariant, string> = {
    default: 'bg-card text-card-foreground',
    elevated: 'bg-card text-card-foreground shadow-neo-lg',
    muted: 'bg-muted text-foreground',
    accent: 'bg-accent text-accent-foreground',
    success: 'bg-success/10 text-foreground',
    warning: 'bg-warning/10 text-foreground',
    info: 'bg-info/10 text-foreground',
    danger: 'bg-destructive/10 text-foreground',
  };

  return cn(
    // Base brutalist box styling
    'rm-box',
    // Non-interactive cards skip the hover translate
    isStatic && 'hover:transform-none hover:translate-x-0 hover:translate-y-0',
    sizeClasses[size],
    variantClasses[variant],
  );
};

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, size, static: isStatic, ...props }, ref) => {
    return (
      <div
        ref={ref}
        data-variant={variant}
        data-size={size}
        className={cn(
          cardVariants({ variant, size, static: isStatic }),
          className,
        )}
        {...props}
      />
    );
  },
);
Card.displayName = 'Card';

export default Card;