FROM python:3.8-buster

# Install nodejs
RUN apt-get update && apt-get install -y curl
RUN curl -o- https://raw.githubusercontent.com/creationix/nvm/v0.34.0/install.sh | bash && \
    . /root/.bashrc && \
    sleep 1 && \
    nvm install 12.18.2 && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/node /usr/local/bin/node && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/npm /usr/local/bin/npm && \
    ln -s /root/.nvm/versions/node/v12.18.2/bin/npx /usr/local/bin/npx

# Install pipenv
RUN pip install pipenv

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:user

# Install python dependencies
WORKDIR /app
COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv install --dev

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
CMD ["pipenv", "run", "python", "-u", "app.py"]