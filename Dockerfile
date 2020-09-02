FROM registry.access.redhat.com/ubi8/python-38

WORKDIR /archspec
COPY . .

USER root

RUN dnf update -y && dnf install git python38 python3-pip -y
RUN pip3 install poetry tox-gh-actions coverage
RUN pip3 install archspec
RUN dnf clean all

RUN useradd archspec
USER archspec

ENTRYPOINT ["archspec"]
