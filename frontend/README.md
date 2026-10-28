# ToneTrace AI — Mobile Web Frontend

The frontend for ToneTrace AI is a mobile-first web client engineered for cosmetic formulation analysis, ingredient evidence browsing, product scanning, and routine management.

---

## 1. Architecture & Design Principles

- **Mobile-First Ergonomics**: Designed for a **390px baseline** (iPhone 14/15/16), tested across 360px (compact Android) and 430px (iPhone Pro Max / Plus).
- **Desktop Centering**: On viewports wider than 430px, the application centers a maximum-430px device shell (`max-w-[430px]`) rather than stretching into an unergonomic desktop layout.
- **Scientific Skincare Aesthetics**: Obsidian slate background (`#080C0F`), translucent glassmorphic surfaces (`glass-panel`), clinical emerald accents (`#10B981`), luxury champagne formulation highlights (`#E0C39E`), and amber/rose alerts for sensitivities and reactions.
- **Fail-Safe Loading**: Initial branded loading state features a 6-to-8 second timeout fallback so the application can never spin indefinitely when the backend is offline.
- **Zero Hallucination Policy**: Business pages display strictly verified backend responses or explicit unconfigured states; no synthetic mock data is shown on active feature pages.

---

## 2. Technology Stack

- **Runtime & Build**: Node.js 20+, Vite 6, React 19, TypeScript 5.8+
- **Styling**: Tailwind CSS with custom design tokens and `@tailwindcss` utilities
- **Icons**: Lucide React
- **Unit & Integration Testing**: Vitest, `@testing-library/react`, JSDOM
- **Package Manager**: `pnpm` (or `npm`)

---

## 3. Environment Configuration & Proxy Strategy

### 3.1 Environment File Setup
Copy the example environment configuration:
```bash
cp .env.example .env
```

| Variable | Default (Local) | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | *(empty)* | If empty, Vite dev server proxies `/api` and `/health` requests to `http://localhost:8000`. If specified (e.g. `http://localhost:8000`), requests use direct CORS. |
| `VITE_APP_VERSION` | `0.1.0` | Client application release identifier. |
| `VITE_ENABLE_DEV_SHOWCASE`| `true` | Toggles visibility of the design system showcase gallery in development. |

### 3.2 CORS & Proxy Approach
The FastAPI backend allows `http://localhost:3000` and `http://127.0.0.1:3000` via its `ALLOWED_CORS_ORIGINS` configuration.

Two operational approaches are supported:
1. **Vite Proxy (Recommended for local dev)**: Keep `VITE_API_BASE_URL` empty. Vite proxies `/api` and `/health` to `http://localhost:8000`, bypassing browser CORS preflight overhead.
2. **Direct CORS**: Set `VITE_API_BASE_URL=http://localhost:8000`. The browser connects directly to FastAPI with credentials and custom headers exposed (`X-Request-ID`).

---

## 4. Development & Testing Commands

From the `frontend/` directory:

```bash
# Install dependencies
pnpm install --ignore-scripts

# Start local development server on port 3000
pnpm dev

# Run strict TypeScript typecheck
pnpm typecheck

# Execute unit and layout tests
pnpm test

# Build production bundle
pnpm build
```

---

## 5. Design System Showcase

A dedicated development showcase route is available on the navigation bar (**Showcase** tab). It verifies:
- Color tokens & type scale
- Button variants (Primary Clinical, Luxury Champagne, Secondary, Outline, Danger, Loading)
- Clinical status chips (Verified, Caution, Adverse, Luxury, INCI)
- Translucent glassmorphic cards (Default, Elevated, Interactive, Accent)
- Form inputs with focus rings, helpers, and validation states
- Shimmer skeleton loaders
- Branded loading animation with simulated timeout recovery
- Structured API error recovery banner with request ID correlation
