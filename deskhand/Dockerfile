# Deskhand: the live agent target. The build context is deskhand/ alone, so the rest of
# the Langfail repo (answer keys, held-out suites) is never sent to a builder:
#   podman build -t deskhand deskhand/
# Never publish this to the internet: every gap in it is real.
# Digest read from the registry on 2026-11-05 (podman image inspect), not typed in.
FROM docker.io/library/python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

# Same versions as the repo's own venv.
RUN useradd --create-home --uid 10001 deskhand \
 && pip install --no-cache-dir "Flask==3.1.3" "requests==2.34.2"

WORKDIR /app
# Only the runtime modules: tests, deploy scripts and the answer key never enter a layer.
COPY *.py deskhand/
RUN mkdir -p /app/var && chown deskhand /app/var
USER deskhand

# The canary stays on loopback inside the container; only the chat port is exposed.
EXPOSE 8300
ENTRYPOINT ["python", "-m", "deskhand", "--db", "/app/var/deskhand.db", "serve", \
            "--host", "0.0.0.0", "--port", "8300", "--help-base", "http://127.0.0.1:8300", \
            "--canary-host", "127.0.0.1"]
CMD ["--backend", "stub"]
