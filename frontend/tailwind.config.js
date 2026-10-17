/** @type {import('tailwindcss').Config} */
export default {
  // Dark mode toggled by `class="dark"` on <html>. Also respects
  // `prefers-color-scheme` via the :root:not(.light) media query in
  // index.css when no explicit class is set.
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // ----------------------------------------------------------------
      // Colors: shadcn/ui-compatible semantic tokens driven by CSS vars.
      // ----------------------------------------------------------------
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // New semantic tokens (PR1)
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },
      },

      // ----------------------------------------------------------------
      // Border radius — brutalist default (0) preserved. New `sm`/`md`
      // tokens available for components that want softer corners
      // (badges, avatars, pill buttons).
      // ----------------------------------------------------------------
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) + 2px)",
        sm: "calc(var(--radius) + 4px)",
        // Opt-in softer radii (use `rounded-soft-sm` etc.)
        "soft-sm": "4px",
        "soft-md": "6px",
        "soft-lg": "8px",
      },

      // ----------------------------------------------------------------
      // Box shadows — neo-brutalist hard offsets + soft layered for
      // floating UI. CSS vars in index.css keep the colors theme-aware.
      // ----------------------------------------------------------------
      boxShadow: {
        // Brutalist hard offset
        'neo-xs': 'var(--shadow-neo-xs)',
        'neo-sm': 'var(--shadow-neo-sm)',
        'neo': 'var(--shadow-neo)',
        'neo-md': 'var(--shadow-neo-md)',
        'neo-lg': 'var(--shadow-neo-lg)',
        'neo-xl': 'var(--shadow-neo-xl)',
        // Soft layered for floating UI
        'soft-sm': 'var(--shadow-soft-sm)',
        'soft': 'var(--shadow-soft)',
        'soft-lg': 'var(--shadow-soft-lg)',
      },

      // ----------------------------------------------------------------
      // Typography scale (1.25 ratio, Major Third). Tailwind keeps the
      // default `xs..9xl` so existing classes don't break — these are
      // additional named slots for component-level tokens.
      // ----------------------------------------------------------------
      fontSize: {
        // CSS-var-driven sizes for semantic use
        'token-xs': 'var(--font-size-xs)',
        'token-sm': 'var(--font-size-sm)',
        'token-base': 'var(--font-size-base)',
        'token-lg': 'var(--font-size-lg)',
        'token-xl': 'var(--font-size-xl)',
        'token-2xl': 'var(--font-size-2xl)',
        'token-3xl': 'var(--font-size-3xl)',
        'token-4xl': 'var(--font-size-4xl)',
        'token-5xl': 'var(--font-size-5xl)',
        'token-6xl': 'var(--font-size-6xl)',
        'token-7xl': 'var(--font-size-7xl)',
      },
      lineHeight: {
        'token-tight': 'var(--leading-tight)',
        'token-snug': 'var(--leading-snug)',
        'token-normal': 'var(--leading-normal)',
        'token-relaxed': 'var(--leading-relaxed)',
      },
      letterSpacing: {
        'token-tighter': 'var(--tracking-tighter)',
        'token-tight': 'var(--tracking-tight)',
        'token-wide': 'var(--tracking-wide)',
        'token-widest': 'var(--tracking-widest)',
      },

      // ----------------------------------------------------------------
      // Motion — semantic durations + easings.
      // ----------------------------------------------------------------
      transitionDuration: {
        'instant': 'var(--duration-instant)',
        'fast': 'var(--duration-fast)',
        'base': 'var(--duration-base)',
        'slow': 'var(--duration-slow)',
        'slower': 'var(--duration-slower)',
      },
      transitionTimingFunction: {
        'standard': 'var(--ease-standard)',
        'enter': 'var(--ease-enter)',
        'exit': 'var(--ease-exit)',
        'emphasis': 'var(--ease-emphasis)',
      },

      // ----------------------------------------------------------------
      // Spacing — 8pt grid as named tokens (optional, use sparingly
      // alongside Tailwind's numeric scale).
      // ----------------------------------------------------------------
      spacing: {
        'space-1': 'var(--space-1)',
        'space-2': 'var(--space-2)',
        'space-3': 'var(--space-3)',
        'space-4': 'var(--space-4)',
        'space-6': 'var(--space-6)',
        'space-8': 'var(--space-8)',
        'space-12': 'var(--space-12)',
        'space-16': 'var(--space-16)',
        'space-24': 'var(--space-24)',
        'space-32': 'var(--space-32)',
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}