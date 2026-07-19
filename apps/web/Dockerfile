# Production image: Next.js yönetim paneli (standalone output).
#
# Build context: repo KÖKÜ olmalı (`docker build -f apps/web/Dockerfile .`)
# — pnpm workspace (`pnpm-workspace.yaml`, kök `package.json`,
# `tests/e2e/package.json`) doğru bağımlılık çözümlemesi için gerekli,
# `apps/web` tek başına yeterli değildir.

FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH" \
    CI=true \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

# ─── deps: yalnız workspace manifest'leri + lockfile (kaynak değişse bile cache kalır) ─
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY tests/e2e/package.json tests/e2e/package.json
RUN pnpm install --frozen-lockfile --filter=@ivac/web...

# ─── builder: gerçek kaynak + production build ─────────────────────────────
FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
COPY apps/web ./apps/web

# NEXT_PUBLIC_* değişkenleri `next build` sırasında client bundle'a
# GÖMÜLÜR — yalnız runtime env olarak vermek yeterli değildir, build-arg
# olarak da geçirilmelidir (gerçek production domain'iyle).
ARG NEXT_PUBLIC_API_URL=https://api.example.invalid
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN pnpm --filter @ivac/web build

# ─── runner: yalnız standalone çıktı + statik varlıklar ────────────────────
FROM node:22-slim AS runner
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

RUN addgroup --system ivac && adduser --system --ingroup ivac ivac

COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static
# NOT: `apps/web/public/` şu an mevcut değil (repo'da yok). Eklenirse burada
# `COPY --from=builder /repo/apps/web/public ./apps/web/public` satırı da
# gerekir — Next.js standalone çıktısı public/ dizinini otomatik kopyalamaz.

USER ivac

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.status===200?0:1)).catch(()=>process.exit(1))"]

# `.next/standalone` çıktısı, apps/web workspace paketinin repo köküne göre
# yolunu korur — gerçek server.js `apps/web/server.js` altındadır.
CMD ["node", "apps/web/server.js"]
