// Vikunja MCP - Developed by acidvegas in Go (https://git.acid.vegas)
// vikunja-mcp/main.go

package main

import (
	"context"
	_ "embed"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

//go:embed instructions.txt
var instructions string

type config struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

func main() {
	log.SetFlags(0)
	log.SetPrefix("vikunja-mcp: ")

	vikunjaURL := strings.TrimRight(os.Getenv("VIKUNJA_URL"), "/")
	if vikunjaURL == "" {
		log.Fatal("VIKUNJA_URL is not set")
	}
	token := os.Getenv("VIKUNJA_TOKEN")
	if token == "" {
		log.Fatal("VIKUNJA_TOKEN is not set")
	}

	defaultTransport := envOr("VIKUNJA_MCP_TRANSPORT", "stdio")
	defaultHost := envOr("VIKUNJA_MCP_HOST", "127.0.0.1")
	defaultPort := 8000
	if v := os.Getenv("VIKUNJA_MCP_PORT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			defaultPort = n
		}
	}

	var transport, host string
	var port int
	flag.StringVar(&transport, "transport", defaultTransport, "Transport: stdio or http")
	flag.StringVar(&transport, "t", defaultTransport, "Transport (shorthand)")
	flag.StringVar(&host, "host", defaultHost, "Host for http transport")
	flag.IntVar(&port, "port", defaultPort, "Port for http transport")
	flag.Parse()

	cfg := &config{
		baseURL:    vikunjaURL + "/api/v1",
		token:      token,
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}

	spec, err := loadSpec(cfg.baseURL + "/docs.json")
	if err != nil {
		log.Fatalf("spec load failed: %v", err)
	}
	patchSpec(spec)

	server := mcp.NewServer(
		&mcp.Implementation{Name: "vikunja", Version: "1.0.0"},
		&mcp.ServerOptions{Instructions: instructions},
	)

	n := registerTools(server, cfg, spec)
	log.Printf("loaded %d tools from vikunja spec", n)

	switch strings.ToLower(transport) {
	case "stdio":
		if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
			log.Fatal(err)
		}
	case "http":
		handler := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return server }, nil)
		mux := http.NewServeMux()
		mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "text/plain")
			_, _ = w.Write([]byte("ok"))
		})
		mux.Handle("/", handler)
		addr := fmt.Sprintf("%s:%d", host, port)
		log.Printf("http listening on %s", addr)
		if err := http.ListenAndServe(addr, mux); err != nil {
			log.Fatal(err)
		}
	default:
		log.Fatalf("unknown transport: %s (use stdio or http)", transport)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
