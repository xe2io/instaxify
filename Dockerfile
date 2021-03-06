FROM alpine:latest
RUN apk --no-cache add \
    python3 \
    py3-pillow \
    py3-magic \
    py3-requests \
    && mkdir /cert \
    && adduser -h / -D -H instaxify 

USER instaxify
# Run requires script in /, calibration profiles in /calibration
ADD calibration /calibration
ADD instaxify_service.py /

EXPOSE 8443

ENTRYPOINT ["python3", "-u"]
CMD ["/instaxify_service.py"]
