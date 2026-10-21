// Package web embeds the HTML templates into the binary,
// so the app doesn't depend on where it runs from (local, Docker, etc).
package web

import "embed"

// FS holds the templates/ directory.
//
//go:embed templates/*.html
var FS embed.FS
