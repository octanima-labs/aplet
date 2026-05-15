FROM fedora:latest

RUN dnf install -y \
      bash \
      ca-certificates \
      git \
      python3 \
      python3-pip \
 && dnf clean all

WORKDIR /tmp/work
