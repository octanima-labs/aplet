FROM opensuse/leap:15.6

RUN zypper --non-interactive refresh \
 && zypper --non-interactive install -y \
      bash \
      ca-certificates \
      git \
      python3 \
      python3-pip \
 && zypper clean --all

WORKDIR /tmp/work
