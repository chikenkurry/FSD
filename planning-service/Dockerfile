FROM golang:1.27.2 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY app ./app
RUN go test ./app/internal/...
# GO_COVER=1 builds a coverage-instrumented binary for end-to-end coverage runs
# (see scripts/planning-coverage.sh); normal images leave it unset.
ARG GO_COVER=
RUN CGO_ENABLED=0 go build ${GO_COVER:+-cover -coverpkg=./app/...} -o /planning ./app/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /planning /planning
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 CMD ["/planning", "healthcheck"]
ENTRYPOINT ["/planning"]
