FROM alpine:3.22.6@sha256:365499d9dccb7c8cfaffef995a6c382e71174585e0556f6476ead1c5971c39fb

RUN apk add --no-cache acl

COPY entrypoint.sh /usr/local/bin/workspace-acl-helper
RUN chmod 0555 /usr/local/bin/workspace-acl-helper

USER 65534:65534
ENTRYPOINT ["/usr/local/bin/workspace-acl-helper"]
