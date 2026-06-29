FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install

# Cache-Buster: Der Deploy übergibt bei jedem Commit den aktuellen Git-SHA als
# Build-Arg. Da sich der Wert dann ändert, invalidiert Docker ab hier den Cache
# zuverlässig – auch wenn 'build --no-cache' vom Buildx/Bake-Backend ignoriert
# wird. So wird der Quellcode-COPY + 'npm run build' garantiert neu ausgeführt.
ARG GIT_SHA=dev
RUN echo "build $GIT_SHA"

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
