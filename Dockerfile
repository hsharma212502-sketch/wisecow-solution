

FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="Wisecow" \
      org.opencontainers.image.description="Cow wisdom web server (fortune | cowsay over HTTP)" \
      org.opencontainers.image.source="https://github.com/nyrahul/wisecow"


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fortune-mod \
        fortunes \
        cowsay \
        netcat-openbsd \
        bash \
    && rm -rf /var/lib/apt/lists/*


ENV PATH="/usr/games:${PATH}"


RUN useradd --create-home --shell /bin/bash wisecow
WORKDIR /home/wisecow


COPY wisecow.sh /home/wisecow/wisecow.sh
RUN chmod +x /home/wisecow/wisecow.sh && chown -R wisecow:wisecow /home/wisecow

USER wisecow


EXPOSE 4499


HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD nc -z localhost 4499 || exit 1

ENTRYPOINT ["/home/wisecow/wisecow.sh"]
