FROM python:3.10-bullseye

# Updates
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get clean

# Install nodejs
RUN cd /opt && \
    wget https://nodejs.org/dist/v18.12.0/node-v18.12.0-linux-x64.tar.xz && \
    tar -xf node-v18.12.0-linux-x64.tar.xz && \
    ln -s /opt/node-v18.12.0-linux-x64/bin/node /usr/local/bin/node && \
    ln -s /opt/node-v18.12.0-linux-x64/bin/npm /usr/local/bin/npm

# Switch to unprivileged user
WORKDIR /app
RUN useradd -u 1000 -o -ms /bin/bash user
RUN chown -R user:user /app
USER user:user

# Install python dependencies
RUN python -m pip install --upgrade pip
RUN python -m pip install poetry
COPY poetry.lock .
COPY pyproject.toml .
RUN python -m poetry install

# Install node deps for frontend
RUN mkdir frontend
COPY frontend/package.json frontend
COPY frontend/package-lock.json frontend
USER root:root
RUN chown -R user:user frontend 
USER user:user
RUN cd frontend && npm install

# Install node deps for admin frontend
RUN mkdir admin-frontend
COPY admin-frontend/package.json admin-frontend
COPY admin-frontend/package-lock.json admin-frontend
USER root:root
RUN chown -R user:user admin-frontend 
USER user:user
RUN cd admin-frontend && npm install

# Copy code
COPY . .
USER root:root
RUN chown -R user:user .
USER user:user

# Build the frontends
RUN cd frontend && ./build.sh
RUN cd admin-frontend && ./build.sh

EXPOSE 8000
# CMD ["python", "-m", "poetry", "run", "flask", "run", "-h", "0.0.0.0", "-p", "8080"]
CMD ["python", "-m", "poetry", "run", "gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "'web:app'", "--access-logfile=-"]