# ---- build ----
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
COPY web2 ./web2
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/armor-gw ./cmd/server

# ---- run ----
FROM alpine:3.20
RUN adduser -D -u 10001 armor
WORKDIR /app
COPY --from=build /out/armor-gw /app/armor-gw
USER armor
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8788/health || exit 1
ENTRYPOINT ["/app/armor-gw"]
