FROM jupyterhub/jupyterhub:1.3 AS builder

# dev tools
RUN apt-get update && \
    apt-get install -y \
        gcc \
        libpq-dev \
        git \
        python3-dev && \
    apt-get autoclean && apt-get clean && apt-get autoremove

# freeze version of pip packages from upstream image
RUN python3 -m pip list --format freeze > /tmp/requirements

WORKDIR /tmp

# Authenticator
RUN python3 -m pip wheel --wheel-dir wheelhouse --constraint requirements \
    git+https://github.com/cwaldbieser/jhub_remote_user_authenticator.git

# Spawner
RUN mkdir /tmp/spawner
ADD ./spawner /tmp/spawner/
RUN python3 -m pip wheel --wheel-dir wheelhouse --constraint requirements \
    git+https://github.com/jupyterhub/dockerspawner.git && \
    python3 -m pip wheel --wheel-dir wheelhouse --constraint requirements /tmp/spawner

# DB
RUN python3 -m pip wheel --wheel-dir wheelhouse --constraint requirements \
    psycopg2

FROM jupyterhub/jupyterhub:1.3

# dind
RUN apt-get update && \
    apt-get install -y make && \
    apt-get autoclean && apt-get clean && apt-get autoremove && \
    curl -fsSL https://get.docker.com/ | sh

# DB
RUN apt-get update && \
    apt-get install -y \
        libpq5 && \
    apt-get autoclean && apt-get clean && apt-get autoremove

# install the wheels from first stage
COPY --from=builder /tmp/wheelhouse /tmp/wheelhouse
RUN python3 -m pip install --no-cache /tmp/wheelhouse/*

# cull servers
ADD cull_idle_servers.py /usr/local/bin/cull_idle_servers.py

# Resources
RUN mkdir /var/jupyterhub
ADD jupyterhub_config.py /srv/jupyterhub/
ADD get_user_id.sh /
RUN chmod +x /get_user_id.sh
RUN apt-get install -y netcat-openbsd \
    && apt-get autoremove -y \
    && apt-get clean -y

EXPOSE 8000
EXPOSE 8081
