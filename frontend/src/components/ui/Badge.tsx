/**
 * Badge — primitive tag/label built on the brutalist design system.
 *
 * Variants:
 *   - default  → black bg, white text (high-emphasis marker)
 *   - primary  → primary bg, primary-foreground text (brand marker)
 *   - secondary → secondary bg (orange), secondary-foreground text
 *   - outline  → transparent bg, black border, foreground text (subtle)
 *   - success  → success/15 bg, success-foreground text
 *   - warning  → warning/15 bg, warning-foreground text
 *   - info     → info/15 bg, info-foreground text
 *   - danger   → destructive/15 bg, destructive-foreground text
 *
 * Sizes: sm, md.
 *
 * Backed by the `.rm-tag` base class in index.css.
 */

import * as React from 'react';
import { cn } from '../../lib/utils';

export type BadgeVariant =
  | 'default'
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'success'
  | 'warning'
  | 'info'
  | 'danger';

export type BadgeSize = 'sm' | 'md';

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
}

export const badgeVariants = ({
  variant = 'default',
  size = 'sm',
}: {
  variant?: BadgeVariant;
  size?: BadgeSize;
}): string => {
  const sizeClasses: Record<BadgeSize, string> = {
    sm: 'px-2.5 py-1 text-[10px]',
    md: 'px-3 py-1.5 text-xs',
  };

  const variantClasses: Record<BadgeVariant, string> = {
    default: 'bg-foreground text-background',
    primary: 'bg-primary text-primary-foreground',
    secondary: 'bg-secondary text-secondary-foreground',
    outline: 'bg-card text-foreground',
    success: 'bg-success/15 text-success border-success',
    warning: 'bg-warning/15 text-warning-foreground border-warning',
    info: 'bg-info/15 text-info border-info',
    danger: 'bg-destructive/15 text-destructive border-destructive',
  };

  return cn('rm-tag', sizeClasses[size], variantClasses[variant]);
};

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <span
        ref={ref}
        data-variant={variant}
        data-size={size}
        className={cn(badgeVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Badge.displayName = 'Badge';

export default Badge;