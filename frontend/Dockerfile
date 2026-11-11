# Stage 1: Build frontend bundle with pinned Node image
FROM node:22.14.0-alpine3.21 AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source and build production bundle
COPY . .
RUN npm run build

# Stage 2: Production web server with pinned Nginx image
FROM nginx:1.27.5-alpine

# Copy built SPA artifacts
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx proxy configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Configure ownership for non-root where possible
RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html /etc/nginx/conf.d

EXPOSE 80

HEALTHCHECK --interval=5s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

