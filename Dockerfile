FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 bubblewrap ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && chmod u-s /usr/bin/bwrap \
    && mkdir -p /runner /source /snapshots /evidence /tmp/home

ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp/home LC_ALL=C.UTF-8
WORKDIR /runner/scripts
USER 65534:65534
CMD ["/usr/bin/python3", "run.py", "--help"]
