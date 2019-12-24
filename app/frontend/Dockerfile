FROM node:8.17-buster

# Copy code
COPY . /app
WORKDIR /app

# Install dependencies
RUN npm install

# Build
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]