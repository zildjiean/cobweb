FROM node:20-alpine AS deps
WORKDIR /app
COPY apps/web/package.json ./
RUN corepack enable && corepack prepare pnpm@9 --activate \
    && pnpm install --no-frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./
RUN corepack enable && corepack prepare pnpm@9 --activate \
    && pnpm build

FROM node:20-alpine AS runner
ENV NODE_ENV=production PORT=3000
WORKDIR /app
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O- http://localhost:3000 || exit 1
CMD ["node", "server.js"]
