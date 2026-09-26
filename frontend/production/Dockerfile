# Track B frontend image — Vite dev server (pending local run).
# For a hackathon demo we serve the Vite dev server; for a real deployment,
# `npm run build` + an nginx static image would replace this.
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
