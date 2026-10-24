FROM golang:1.27.2 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY app ./app
RUN go test ./app/internal/...
RUN CGO_ENABLED=0 go build -o /planning ./app/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /planning /planning
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 CMD ["/planning", "healthcheck"]
ENTRYPOINT ["/planning"]
