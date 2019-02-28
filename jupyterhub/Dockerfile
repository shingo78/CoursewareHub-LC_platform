FROM jupyterhub/jupyterhub:0.9.4

# dind
RUN apt-get update && apt-get install -y make && apt-get autoclean && apt-get clean && apt-get autoremove
RUN curl -fsSL https://get.docker.com/ | sh

# Authenticator
RUN pip --no-cache-dir install git+https://github.com/cwaldbieser/jhub_remote_user_authenticator.git

# Spawner
RUN mkdir /tmp/spawner
ADD ./spawner /tmp/spawner/
RUN pip --no-cache-dir install git+https://github.com/yacchin1205/dockerspawner.git@fix/incompatible-volume-settings && \
    cd /tmp/spawner; pip --no-cache-dir install .

# DB
RUN apt-get install -y libpq-dev \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && pip --no-cache-dir install psycopg2

# Resources
RUN mkdir /var/jupyterhub
ADD jupyterhub_config.py /srv/jupyterhub/

# Configurations
RUN mkdir /srv/jupyterhub_users/ && touch /srv/jupyterhub_users/userlist

EXPOSE 8000
EXPOSE 8081