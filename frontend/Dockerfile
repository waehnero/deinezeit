FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
# `npm ci` statt `npm install`: installiert exakt den Stand aus package-lock.json
# und bricht ab, wenn Lockfile und package.json auseinanderlaufen. Mit
# `npm install` löste jeder Image-Build die Abhängigkeiten neu auf — zwei
# Deploys ohne Codeänderung konnten verschiedene Pakete enthalten, und das
# Lockfile fehlte zeitweise ganze Pakete (Audit BUG-003).
RUN npm ci --no-audit --no-fund

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
