FROM registry.xe2/debian:stretch-slim

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y \
    imagemagick \
    inotify-tools \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -d / -M instaxify \
    && mkdir -p /input /output /completed

ADD auto_instaxify.sh instaxify.sh instaxify_this.sh /
ADD calibration /calibration
USER instaxify

# Run auto_instaxify.sh which will by default watch /input
# /input, /output, and /completed should be volume-mounted from host
CMD ["/auto_instaxify.sh"]
