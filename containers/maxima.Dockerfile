FROM debian:stable-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends maxima maxima-doc && \
    rm -rf /var/lib/apt/lists/*

ENV MAXIMA_NOHELP=1
# default entrypoint always runs maxima in quiet mode
ENTRYPOINT ["maxima", "--very-quiet", "--batch-string"]