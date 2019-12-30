FROM postgres:12

# Copy init scripts
COPY docker-entrypoint-initdb.d /docker-entrypoint-initdb.d

# Use the default config
RUN cp /usr/share/postgresql/postgresql.conf.sample /etc/postgresql/postgresql.conf

# Switch to unprivileged user
RUN useradd -u 1000 -o -ms /bin/bash user
USER user:postgres

RUN postgres -c 'config_file=/etc/postgresql/postgresql.conf'