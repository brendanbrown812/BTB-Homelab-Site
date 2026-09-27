FROM node:24-bookworm-slim AS build
WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci --include=dev --include=optional

ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY . .
RUN npm run build

FROM node:24-bookworm-slim
WORKDIR /app

COPY --from=build /app/package.json /app/package-lock.json /app/.npmrc ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/scripts/sites-env.mjs ./scripts/sites-env.mjs

EXPOSE 3000

CMD ["npm", "run", "start"]
