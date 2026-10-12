FROM golang:1.27.2 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY app ./app
RUN CGO_ENABLED=0 go build -o /planning ./app/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /planning /planning
EXPOSE 8080
ENTRYPOINT ["/planning"]
