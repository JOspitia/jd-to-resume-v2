/**
 * Button — primitive component built on the brutalist design system.
 *
 * Variants:
 *   - primary      → royal blue, for the main CTA (Generate, Open, Submit)
 *   - secondary    → orange, for secondary positive actions (Translate)
 *   - success      → green, for confirm actions (Accept, Approve)
 *   - warning      → yellow, for attention actions (Re-generate, Edit)
 *   - destructive  → red, for destructive actions (Reset, Delete)
 *   - outline      → white bg + black border, for neutral actions (Back)
 *   - ghost        → no border/shadow, for tertiary actions
 *
 * Sizes: sm, md, lg.
 *
 * The base `.rm-btn` class lives in index.css; variant + size layers
 * on top via data attributes. CVA-style API for type-safe variants.
 */

import * as React from 'react';
import { cn } from '../../lib/utils';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'destructive'
  | 'outline'
  | 'ghost';

export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** When true, render an <a> instead. Useful for link-style CTAs. */
  asChild?: boolean;
}

/**
 * Variant → tailwind utility classes. Lives outside the component so
 * the same map can be reused by link variants or future icon wrappers.
 */
export const buttonVariants = ({
  variant = 'primary',
  size = 'md',
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
}): string => {
  const sizeClasses: Record<ButtonSize, string> = {
    sm: 'px-3 py-1.5 text-xs gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-4 text-base gap-2.5',
  };

  const variantClasses: Record<ButtonVariant, string> = {
    primary:
      'bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/95',
    secondary:
      'bg-secondary text-secondary-foreground hover:bg-secondary/90 active:bg-secondary/95',
    success:
      'bg-success text-success-foreground hover:bg-success/90 active:bg-success/95',
    warning:
      'bg-warning text-warning-foreground hover:bg-warning/90 active:bg-warning/95',
    destructive:
      'bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/95',
    outline:
      'bg-card text-foreground hover:bg-accent active:bg-accent/80',
    ghost:
      'bg-transparent text-foreground hover:bg-accent active:bg-accent/80 shadow-none border-transparent',
  };

  return cn(
    // Base brutalist button styling
    'rm-btn',
    // Disabled state
    'disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:transform-none',
    // Inline-flex for icon alignment
    'inline-flex items-center justify-center',
    // Variant + size
    variantClasses[variant],
    sizeClasses[size],
  );
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = 'button', ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        data-variant={variant}
        data-size={size}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';

export default Button;