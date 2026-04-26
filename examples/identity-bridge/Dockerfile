FROM node:22-slim AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY tsconfig.json ./
COPY src/ src/
RUN pnpm run build

FROM node:22-slim
WORKDIR /app
COPY --from=build /app/dist dist/
COPY --from=build /app/node_modules node_modules/
COPY --from=build /app/package.json .
COPY src/views/ dist/views/
EXPOSE 4100
CMD ["node", "dist/index.js"]
