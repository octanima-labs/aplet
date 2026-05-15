FROM rockylinux:9

RUN yum install -y \
      bash \
      ca-certificates \
      git \
      python3 \
      python3-pip \
 && yum clean all

WORKDIR /tmp/work
