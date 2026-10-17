import { Moon, Sun } from 'lucide-react';

import { useTheme } from '../hooks/useTheme';
import { Button } from './ui/Button';

/**
 * ThemeToggle — PR6 dark mode toggle button.
 *
 * Renders a single brutalist button that flips between light and dark
 * themes. The actual re-tinting is handled by the `.dark` CSS class
 * on `<html>` (set by `useTheme`), which activates the dark palette
 * defined in index.css.
 *
 * Accessibility:
 *   - `aria-label` announces the action with the resulting theme
 *     ("Cambiar a tema oscuro" / "Cambiar a tema claro") rather than
 *     the current state, which is the recommended pattern for theme
 *     toggles (the action target, not the current).
 *   - `aria-pressed` reflects whether the toggle is in the "dark
 *     enabled" state, for assistive tech that surfaces it.
 *   - The Sun/Moon icons are decorative (aria-hidden) since the
 *     aria-label carries the semantic.
 */

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';
  const label = isDark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';

  return (
    <Button
      variant="outline"
      size="md"
      onClick={toggleTheme}
      aria-label={label}
      aria-pressed={isDark}
      title={label}
      className={className}
    >
      {isDark ? (
        <Sun className="w-4 h-4" aria-hidden="true" />
      ) : (
        <Moon className="w-4 h-4" aria-hidden="true" />
      )}
      <span className="hidden md:inline">{isDark ? 'Light' : 'Dark'}</span>
    </Button>
  );
}

export default ThemeToggle;