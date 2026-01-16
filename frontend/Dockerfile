FROM node:20-slim AS build
WORKDIR /app


# Configure the API base URL at build time. Default to the nginx /api proxy for
# same-origin routing in production deployments.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}

# Install dependencies with a reproducible lockfile and take advantage of
# Docker layer caching by copying only the lock and manifest first.
COPY frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html /app/
RUN npm ci

# Copy the source code separately so dependency layers remain cached across
# source changes.
COPY frontend/src /app/src
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
