FROM archlinux:latest

RUN pacman -Sy --noconfirm --needed \
      bash \
      ca-certificates \
      git \
      python \
      python-pip \
 && pacman-key --init \
 && pacman-key --populate archlinux \
 && pacman -Scc --noconfirm

WORKDIR /tmp/work
