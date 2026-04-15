// Vikunja MCP - Developed by acidvegas in Go (https://git.acid.vegas)
// vikunja-mcp/spec.go

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

// loadSpec fetches the Vikunja OpenAPI document from the running server.
// Retries up to three times with exponential backoff when the server is
// temporarily unreachable.
func loadSpec(url string) (map[string]any, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		resp, err := client.Get(url)
		if err != nil {
			lastErr = err
		} else {
			if resp.StatusCode >= 400 {
				resp.Body.Close()
				lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
			} else {
				var spec map[string]any
				err := json.NewDecoder(resp.Body).Decode(&spec)
				resp.Body.Close()
				if err == nil {
					return spec, nil
				}
				lastErr = err
			}
		}
		if attempt < 2 {
			delay := time.Duration(1<<(attempt+1)) * time.Second
			log.Printf("spec load attempt %d failed (%v), retrying in %s", attempt+1, lastErr, delay)
			time.Sleep(delay)
		}
	}
	return nil, lastErr
}

var specPatches = []struct {
	path    string
	wrong   string
	correct string
}{
	{"/labels/{id}", "put", "post"},
}

// patchSpec applies known fixes to the upstream Vikunja OpenAPI spec in place.
// The operation is moved from the wrong method to the correct one only when
// the correct method is not already present.
func patchSpec(spec map[string]any) {
	paths, _ := spec["paths"].(map[string]any)
	for _, p := range specPatches {
		node, ok := paths[p.path].(map[string]any)
		if !ok {
			continue
		}
		op, hasWrong := node[p.wrong]
		if !hasWrong {
			continue
		}
		if _, hasCorrect := node[p.correct]; hasCorrect {
			continue
		}
		node[p.correct] = op
		delete(node, p.wrong)
		log.Printf("spec patch: %s %s -> %s", p.path, strings.ToUpper(p.wrong), strings.ToUpper(p.correct))
	}
}

// resolveRef follows a JSON Reference pointer inside an OpenAPI spec.
func resolveRef(spec map[string]any, ref string) map[string]any {
	var node any = spec
	for _, part := range strings.Split(strings.TrimPrefix(ref, "#/"), "/") {
		m, ok := node.(map[string]any)
		if !ok {
			return map[string]any{}
		}
		node = m[part]
	}
	if m, ok := node.(map[string]any); ok {
		return m
	}
	return map[string]any{}
}

// openapiToJSON maps an OpenAPI 2 primitive type to a JSON Schema primitive type.
func openapiToJSON(t string) string {
	switch t {
	case "integer", "number", "boolean", "array":
		return t
	case "file":
		return "string"
	default:
		return "string"
	}
}

// resolveBodySchema builds a JSON Schema dict for a body parameter, resolving
// $ref when present. Extracts top-level property names and types from the
// referenced definition so the LLM knows what fields to include.
func resolveBodySchema(param map[string]any, spec map[string]any) map[string]any {
	schema, _ := param["schema"].(map[string]any)
	if schema == nil {
		schema = map[string]any{}
	}
	if ref, ok := schema["$ref"].(string); ok {
		schema = resolveRef(spec, ref)
	}

	if t, _ := schema["type"].(string); t != "object" {
		return map[string]any{"type": "object"}
	}
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		return map[string]any{"type": "object"}
	}

	props := map[string]any{}
	for name, prop := range properties {
		propMap, ok := prop.(map[string]any)
		if !ok {
			continue
		}
		propType, _ := propMap["type"].(string)
		entry := map[string]any{"type": openapiToJSON(propType)}
		if desc, ok := propMap["description"].(string); ok {
			entry["description"] = strings.TrimSpace(desc)
		}
		if propType == "array" {
			if items, ok := propMap["items"].(map[string]any); ok {
				if ref, ok := items["$ref"].(string); ok {
					items = resolveRef(spec, ref)
				}
				itemType, _ := items["type"].(string)
				entry["items"] = map[string]any{"type": openapiToJSON(itemType)}
			}
		}
		props[name] = entry
	}
	return map[string]any{"type": "object", "properties": props}
}
