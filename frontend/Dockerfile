# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.27-alpine AS runtime

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY nginx.main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

RUN mkdir -p /tmp \
    && chown -R appuser:appgroup /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx /tmp

USER appuser

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
