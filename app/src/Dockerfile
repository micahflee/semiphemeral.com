FROM python:3.10-bullseye

# Updates
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y curl && \
    apt-get upgrade -y && \
    apt-get clean

# Install nodejs
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash && \
    . /root/.bashrc && \
    sleep 1 && \
    nvm install 16.14.2 && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/node /usr/local/bin/node && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/npm /usr/local/bin/npm && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/npx /usr/local/bin/npx

# Install poetry
RUN pip install poetry

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:user

# Install python dependencies
WORKDIR /app
COPY poetry.lock .
COPY pyproject.toml .
RUN poetry install

# Copy code
COPY . .

# Webpack the js
USER root:root
RUN cd frontend && npm install
RUN cd frontend && ./build.js
RUN cd admin-frontend && npm install
RUN cd admin-frontend && ./build.js
USER user:user

EXPOSE 8080
CMD ["poetry", "run", "python", "-u", "app.py"]