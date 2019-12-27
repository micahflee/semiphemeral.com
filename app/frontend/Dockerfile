FROM node:8.17-buster

# Copy code
COPY . /app
WORKDIR /app

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
RUN chown -R user:user /app
USER user:user

# Install dependencies
RUN npm install

# Build
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]