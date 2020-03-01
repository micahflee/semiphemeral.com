FROM python:3.8-buster

# Install nodejs
RUN apt-get update && apt-get install -y nodejs npm

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