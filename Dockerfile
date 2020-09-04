FROM registry.access.redhat.com/ubi8/python-38

USER root

RUN dnf update -y && dnf install git python38 python3-pip -y && dnf clean all
RUN pip3 install archspec

RUN useradd archspec
USER archspec

ENTRYPOINT ["archspec"]
