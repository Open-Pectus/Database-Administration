# Open Pectus Database Administration
Manage [Open Pectus](https://github.com/Open-Pectus/Open-Pectus/) aggregator database in a convenient web interface.

Documentation is available at [Read the Docs](https://docs.openpectus.org/latest/).

## Getting started
Run this tool using Docker assuming the aggregator sqlite database is located at `/home/azureuser/data_prd/open_pectus_aggregator.sqlite3`:

```console
docker run --pull=always --detach \
--name openpectus-database-administration \
-h AZR-PECTUS-PRD-DATABASE-ADMINISTRATION \
-v /home/azureuser/data_prd:/data
-p 0.0.0.0:8301:8301/tcp \
ghcr.io/open-pectus/database-administration:main
```

The web interface will be available at http://localhost:8301. Beware that the web interface has no access restrictions.

## Azure Authorization Intregration
The Database Administration web interface can integrated with Azure App Registrations for access control. A client secret must be provided, a Web app redirect url `https://domain.tld/admin/msal` must be specified, and users who should have access must be assigned to an "Administrator" App Role.

To enable the integration, specify the following environment variables when launching the Docker image:
* `AZURE_APPLICATION_CLIENT_ID`
* `AZURE_DIRECTORY_TENANT_ID`
* `AZURE_CLIENT_SECRET`
* `ENABLE_AZURE_AUTHENTICATION=true`

Run the Docker image as follows:
```console
docker run --pull=always --detach \
--name openpectus-database-administration \
-h AZR-PECTUS-PRD-DATABASE-ADMINISTRATION \
-v /home/azureuser/data_prd:/data
-e AZURE_APPLICATION_CLIENT_ID='...' \
-e AZURE_DIRECTORY_TENANT_ID='...' \
-e AZURE_CLIENT_SECRET='...' \
-e ENABLE_AZURE_AUTHENTICATION='true' \
-p 0.0.0.0:8301:8301/tcp \
ghcr.io/open-pectus/database-administration:main
```

## Deployment behind nginx
The Database Administration web interface can be deployed behind nginx reverse proxy. See the sample nginx configuration below in which letsencrypt is used for SSL certificates. The web interface is then available at https://domain.tld/admin/.

```nginx
server {
    if ($host = domain.tld) {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name openpectus.com;
    ssl_certificate /etc/letsencrypt/live/domain.tld/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/domain.tld/privkey.pem; # managed by Certbot
    location /admin/ {
        proxy_pass http://127.0.0.1:8301;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffer_size 128k;
        proxy_buffers 8 128k;
        proxy_busy_buffers_size 256k;
    }
 }
 ```