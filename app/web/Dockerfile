FROM python:3.8-buster

# Install pipenv
RUN pip install pipenv

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:user

# Copy code
COPY . /app
WORKDIR /app

# Install python dependencies
RUN pipenv install --dev

EXPOSE 8080
CMD ["pipenv", "run", "python", "-u", "app.py"]