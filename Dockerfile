FROM python:3.13-alpine AS base

WORKDIR /usr/src/app
RUN mkdir -p /data
COPY dist ./dist/
RUN pip install --no-cache-dir dist/openpectus_database_administration.tar.gz
RUN pip install openpectus --no-deps --no-cache-dir
RUN rm -R ./dist

# Squash layers to reduce image size
FROM scratch
COPY --from=base / /

EXPOSE 8301
CMD pectus-database-administration --host 0.0.0.0 --port 8301 --database /data/open_pectus_aggregator.sqlite3
