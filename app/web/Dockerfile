FROM python:3.8-buster

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

EXPOSE 8080
CMD ["pipenv", "run", "python", "-u", "app.py"]