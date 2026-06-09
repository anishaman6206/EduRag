# EduRag frontend — production Next.js image
#
# Build:    docker build -t edurag-frontend frontend/
# Run:      docker run --rm -p 3000:3000 \
#             --env-file frontend/.env.local edurag-frontend
#
# Multi-stage: deps -> build -> run. The final image is just
# the standalone Next.js output + Node — no source code or
# node_modules at runtime.

# ─────────────────────────────────────────────────────────────────────────
# Stage 1: install deps
# ─────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# ─────────────────────────────────────────────────────────────────────────
# Stage 2: build
# ─────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Public env vars are read at build time by next.config.mjs. We
# pass placeholder values; real values come from the runtime
# environment via the docker-compose env block.
ENV NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder
ENV BACKEND_URL=http://backend:8000
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────
# Stage 3: runtime (standalone Next.js output)
# ─────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# Copy the standalone output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
