# syntax=docker/dockerfile:1

# ---- Stage 1: build the static files with Node ------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Dependencies first, so this layer is cached until package-lock.json changes.
# "npm ci" installs EXACTLY the versions in the lock file (reproducible builds).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


# ---- Stage 2: serve them with nginx ------------------------------------------
# The final image contains nginx and the built files only: no Node, no node_modules.
FROM nginx:stable-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
