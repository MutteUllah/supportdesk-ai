FROM golang:1.24.2-bookworm AS build
ARG MINIO_VERSION=RELEASE.2025-04-22T22-12-26Z
# Docker Hub images and dl.min.io release downloads are unavailable.
# Go verifies this pinned upstream module and its dependency checksums.
RUN CGO_ENABLED=0 GOBIN=/out go install -p 2 -trimpath -ldflags="-s -w" github.com/minio/minio@${MINIO_VERSION} \
    && cp /go/pkg/mod/github.com/minio/minio@*/LICENSE /out/LICENSE

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system minio \
    && useradd --system --gid minio --home-dir /data minio \
    && mkdir -p /data \
    && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /out/LICENSE /usr/share/doc/minio/LICENSE
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
