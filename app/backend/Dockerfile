FROM python:3.7-buster

# Install pipenv
RUN pip install pipenv

# Switch to unprivileged user, and fix permissions for volume
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:user

# Copy code
COPY . /app
WORKDIR /app

# Install python dependencies
RUN pipenv --python /usr/local/bin/python install --dev

EXPOSE 8080
CMD ["pipenv", "run", "python", "-u", "app.py"]