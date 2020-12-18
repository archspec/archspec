# Universal Base Image (UBI) for Python 3.8
# https://developers.redhat.com/products/rhel/ubi
# https://catalog.redhat.com/software/containers/ubi8/python-38/5dde9cacbed8bd164a0af24a
FROM registry.access.redhat.com/ubi8/python-38

USER root

RUN pip3 install --no-cache-dir archspec

RUN useradd archspec
USER archspec

ENTRYPOINT ["archspec"]
