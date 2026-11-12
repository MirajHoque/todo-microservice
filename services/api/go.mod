module github.com/MirajHoque/todo-microservice/services/api

go 1.26.3

require (
	github.com/MirajHoque/todo-microservice/libs/go v0.0.0
	github.com/go-chi/chi/v5 v5.2.5
	github.com/golang-jwt/jwt/v5 v5.3.1
	github.com/jackc/pgx/v5 v5.10.0
	golang.org/x/crypto v0.57.0
)

require (
	github.com/google/uuid v1.6.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	golang.org/x/sync v0.23.0 // indirect
	golang.org/x/text v0.42.0 // indirect
)

// The shared library lives in this same repo, not on the internet:
// "replace" tells Go to read it from the folder instead of downloading it.
// v0.0.0 above is a placeholder — the folder is always used.
replace github.com/MirajHoque/todo-microservice/libs/go => ../../libs/go
