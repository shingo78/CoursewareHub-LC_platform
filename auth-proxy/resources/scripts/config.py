#!/usr/bin/python
import os

hub_name = os.environ['HUB_NAME']
master_fqdn = os.environ['MASTER_FQDN']

with open('/etc/nginx/nginx.conf', 'w') as f:
    f.write('''# For more information on configuration, see:
#   * Official English Documentation: http://nginx.org/en/docs/
#   * Official Russian Documentation: http://nginx.org/ru/docs/

user www-data;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

# Load dynamic modules. See /usr/share/nginx/README.dynamic.
include /usr/share/nginx/modules/*.conf;

events {{
    worker_connections 1024;
}}

http {{
    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';
    #log_format debug_log_fmt "[DEBUG][$time_local] $dbg";

    access_log  /var/log/nginx/access.log  main;

    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    keepalive_timeout   65;
    types_hash_max_size 2048;
    client_max_body_size 50M;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    upstream {master_fqdn} {{
        server {master_fqdn}:443;
    }}

    server {{
        listen 80;
        server_name hub;
        rewrite  ^ https://$host$request_uri? permanent;
    }}

    server {{
        listen 443 ssl;
        server_name hub;
        root /var/www;
        index auth.php login.php logout.php;

        ssl on;
        ssl_certificate "/etc/nginx/certs/auth-proxy.chained.cer";
        ssl_certificate_key "/etc/nginx/certs/auth-proxy.key";

        ssl_ciphers "AES128+EECDH:AES128+EDH";
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains";
        add_header X-Content-Type-Options nosniff;
        resolver_timeout 5s;

        location ^~ /login {{
            rewrite /login /php/login.php permanent;
        }}

        location ^~ /logout {{
            rewrite /logout /php/logout.php permanent;
        }}

        location ^~ /hub/logout {{
            rewrite /hub/logout /php/logout.php permanent;
        }}

        location ^~ /no_author {{
            internal;
            rewrite /no_author /html/no_author.html break;
        }}

        location ~ [^/]\.php(/|$) {{
            fastcgi_split_path_info ^(.+\.php)(/.*)$;
            fastcgi_pass unix:/run/php/php5.6-fpm.sock;
            include fastcgi_params;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_param PATH_INFO $fastcgi_path_info;
            #set $dbg "dbg0: $fastcgi_script_name";
            #access_log /var/log/nginx/debug.log debug_log_fmt;
        }}

        location ^~ /simplesaml {{
            alias /var/www/simplesamlphp/www;

            location ~ ^(?<prefix>/simplesaml)(?<phpfile>.+?\.php)(?<pathinfo>/.*)?$ {{
                fastcgi_pass unix:/run/php/php5.6-fpm.sock;
                fastcgi_index index.php;
                include fastcgi_params;
                fastcgi_param SCRIPT_FILENAME $document_root$phpfile;
                fastcgi_param PATH_INFO $pathinfo if_not_empty;
            }}
        }}

        location / {{
            proxy_pass $scheme://127.0.0.1:$server_port/php/auth.php;
            proxy_set_header X-Reproxy-URI $uri;
            proxy_set_header X-Reproxy-Query $is_args$args;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-NginX-Proxy true;
        }}

        location ^~ /entrance/ {{
            internal;
            set $entrance $upstream_http_x_reproxy_url;
            proxy_pass $entrance;
            set $r_user $upstream_http_x_remote_user;
            proxy_set_header REMOTE_USER $r_user;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-NginX-Proxy true;
        }}

        location ~* /(logo|.*\.(jpg|jpeg|gif|png|css|js|ico|xml|map|woff|ttf))$ {{
            access_log off;
            proxy_pass http://{master_ip}:8000;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-NginX-Proxy true;
        }}

        #location ~* /(user/[^/]*)/(api/kernels/[^/]+/channels|terminals/websocket)/? {{
        location ~* /(api|terminals|files)/.*? {{
            proxy_pass http://{master_ip}:8000;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-NginX-Proxy true;

            # WebSocket support
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }}

    }}
}}'''.format(master_ip=hub_name, master_fqdn=master_fqdn))


cron_secret = os.environ['CRON_SECRET']

with open('/var/www/simplesamlphp/config/module_cron.php', 'w') as f:
    f.write('''<?php
/*
 * Configuration for the Cron module.
 */

$config = array (

        'key' => '{cron_secret}',
        'allowed_tags' => array('daily', 'hourly', 'frequent'),
        'debug_message' => TRUE,
        'sendemail' => FALSE,

);
'''.format(cron_secret=cron_secret))


with open('/var/spool/cron/crontabs/root', 'w') as f:
    f.write('@reboot /bin/sleep 10 && /usr/bin/curl --silent --insecure "https://localhost/simplesaml/module.php/cron/cron.php?key={cron_secret}&tag=daily"\n'.format(cron_secret=cron_secret))
    f.write('0 0 * * * /usr/bin/curl --silent --insecure "https://localhost/simplesaml/module.php/cron/cron.php?key={cron_secret}&tag=daily"\n'.format(cron_secret=cron_secret))

os.chmod('/var/spool/cron/crontabs/root', 0o600)
