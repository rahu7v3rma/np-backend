FROM python:3.11-slim AS builder

WORKDIR /src

# install build (for some package-dependencies) dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y libpq-dev gcc

# only copy the requirements file for the builder
COPY requirements.txt prod_requirements.txt ./

# install python requirements plus gunicorn before copying the code 
# to avoid having to create this layer per every code change
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r prod_requirements.txt && \
    pip install --no-cache-dir gunicorn==21.2.0



FROM node:20-slim AS jsbuilder

WORKDIR /js

COPY js .

RUN npm ci && \
    npm run build && \
    rm webpack_bundles/*.js.map



FROM python:3.11-slim

ARG TARGET_ARCH=amd64

# create non-root user for running the app
RUN addgroup --gid 10001 nonroot && \
    adduser --uid 10000 --ingroup nonroot --home /home/nonroot --disabled-password --gecos "" nonroot

# add tini and use it as the entrypoint
ADD https://github.com/krallin/tini/releases/download/v0.19.0/tini-$TARGET_ARCH /tini
RUN chmod +x /tini
ENTRYPOINT ["/tini", "--"]

# install execution dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y libpq5 procps

WORKDIR /src

# copy all site-packages installed on the builders so we don't need
# gcc, npm or any such heavy machinery
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/
COPY --from=jsbuilder /js/webpack_bundles /js/webpack_bundles
COPY --from=jsbuilder /js/webpack-stats.json /js/webpack-stats.json

# copy the source directory
COPY src/ .

# copy dist env file for the collectstatic command
COPY .env.dist .

ENV ENV=production \
    PYTHONPATH=/src

run rm -rf static/* && \
    DOTENV_FILE=.env.dist python manage.py collectstatic --no-input

EXPOSE 8080

# use the non-root user to run the app
USER nonroot

CMD [ \
    "gunicorn", \
    "--bind", \
    "0.0.0.0:8080", \
    "--workers=3", \
    "--timeout=120", \
    "--log-level=info", \
    "--access-logfile", \
    "-", \
    "--access-logformat", \
    "%({x-forwarded-for}i)s (%(h)s) %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\"", \
    "np_cms.wsgi" \
]
