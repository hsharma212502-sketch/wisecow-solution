# syntax=docker/dockerfile:1
# ---- Wisecow Application Image ----
# The Wisecow app is a bash script that serves "fortune | cowsay" output
# over HTTP using netcat (nc) on port 4499.

FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="Wisecow" \
      org.opencontainers.image.description="Cow wisdom web server (fortune | cowsay over HTTP)" \
      org.opencontainers.image.source="https://github.com/nyrahul/wisecow"

# Install runtime prerequisites:
#  - fortune-mod : generates random adages (provides 'fortune')
#  - fortunes    : the actual fortune cookie databases
#  - cowsay      : renders the adage as an ASCII cow
#  - netcat-openbsd : provides 'nc' with the -N flag used by the app
#  - bash        : the script uses bash-specific features
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fortune-mod \
        fortunes \
        cowsay \
        netcat-openbsd \
        bash \
    && rm -rf /var/lib/apt/lists/*

# cowsay and fortune install their binaries under /usr/games which is not on
# the default PATH. Add it so the script can find them.
ENV PATH="/usr/games:${PATH}"

# Create a non-root user to run the application (security best practice).
RUN useradd --create-home --shell /bin/bash wisecow
WORKDIR /home/wisecow

# Copy the application script and make it executable.
COPY wisecow.sh /home/wisecow/wisecow.sh
RUN chmod +x /home/wisecow/wisecow.sh && chown -R wisecow:wisecow /home/wisecow

USER wisecow

# The app listens on port 4499 by default.
EXPOSE 4499

# A simple health hint: the container is healthy if the port is open.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD nc -z localhost 4499 || exit 1

ENTRYPOINT ["/home/wisecow/wisecow.sh"]
