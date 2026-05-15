FROM ubuntu:24.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      git \
      python3 \
      python3-pip \
      python3-venv

WORKDIR /tmp/work
