FROM python:3.10-bullseye

# Updates
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get clean

# Install poetry
RUN pip install poetry

# Install nodejs
RUN cd /opt && \
    wget https://nodejs.org/dist/v16.15.0/node-v16.15.0-linux-x64.tar.xz && \
    tar -xf node-v16.15.0-linux-x64.tar.xz && \
    ln -s /opt/node-v16.15.0-linux-x64/bin/node /usr/local/bin/node && \
    ln -s /opt/node-v16.15.0-linux-x64/bin/npm /usr/local/bin/npm

# Install python dependencies
WORKDIR /app
COPY poetry.lock .
COPY pyproject.toml .
RUN poetry install

# Install node deps for frontend
RUN mkdir frontend
COPY frontend/package.json frontend
COPY frontend/package-lock.json frontend
RUN cd frontend && npm install

# Install node deps for admin frontend
RUN mkdir admin-frontend
COPY admin-frontend/package.json admin-frontend
COPY admin-frontend/package-lock.json admin-frontend
RUN cd admin-frontend && npm install

# Copy code
COPY . .

# Build the frontend
RUN cd frontend && npm run build

# Build the admin-frontend
RUN cd admin-frontend && npm run build

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:user

EXPOSE 8080
CMD ["poetry", "run", "python", "-u", "app.py"]