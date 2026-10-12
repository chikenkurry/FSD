# FSD_Project_what2do

This branch brings Planning, Participation and Decision code together. The service
snapshot mappings, recommendation API and complete lifecycle still need to be
connected and tested across services.

The Decision Service converts planning and response snapshots into typed inputs
and provides execution adapters and matching algorithms. See
[its README](decision_service/docs/README.md) for examples and local setup, and
[the input contract](decision_service/docs/algorithm-input-shape.md) for the handoff.
The earlier standalone algorithm remains in `decision_service/app/algorithm`;
the current preprocessing adapters use `decision_service/algorithm` and
`decision_service/generic_algorithm`.

Run Planning from `planning-service`:

```sh
docker compose up -d
go run app/api/main.go
```

Participation setup and endpoint contracts are in
[its README](participation-service-main/README.md) and
[API documentation](participation-service-main/docs/API.md).
