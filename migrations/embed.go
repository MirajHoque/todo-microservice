// Package migrations embeds the SQL migration files into the binary,
// so the app doesn't depend on where it runs from (local, Docker, etc).
package migrations

import "embed"

// FS holds every .sql file in this directory.
//
//go:embed *.sql
var FS embed.FS
