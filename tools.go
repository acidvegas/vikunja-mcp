// Vikunja MCP - Developed by acidvegas in Go (https://git.acid.vegas)
// vikunja-mcp/tools.go

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var (
	nameSanitizer = regexp.MustCompile(`[^a-zA-Z0-9_-]+`)
	pathParamRe   = regexp.MustCompile(`\{(\w+)\}`)
)

// sanitizeName turns an OpenAPI operationId into a valid MCP tool name.
func sanitizeName(raw string) string {
	name := nameSanitizer.ReplaceAllString(raw, "_")
	name = strings.Trim(name, "_")
	if len(name) > 64 {
		name = name[:64]
	}
	if name == "" {
		return "op"
	}
	return name
}

type opDescriptor struct {
	method string
	path   string
	params []map[string]any
}

// registerTools walks an OpenAPI 2 spec and registers an MCP tool for every
// allowlisted operation. Returns the number of tools registered.
func registerTools(server *mcp.Server, cfg *config, spec map[string]any) int {
	paths, _ := spec["paths"].(map[string]any)
	count := 0

	for path, methodsAny := range paths {
		methods, ok := methodsAny.(map[string]any)
		if !ok {
			continue
		}
		for method, opAny := range methods {
			switch method {
			case "get", "post", "put", "delete", "patch":
			default:
				continue
			}
			methodU := strings.ToUpper(method)
			if !isAllowlisted(methodU, path) {
				continue
			}
			op, ok := opAny.(map[string]any)
			if !ok {
				continue
			}

			name := toolNameFor(op, method, path)
			desc := toolDescFor(op, methodU, path)
			properties, required, params := buildSchema(op, spec, methodU, path)

			schema := map[string]any{
				"type":       "object",
				"properties": properties,
				"required":   required,
			}
			schemaBytes, err := json.Marshal(schema)
			if err != nil {
				log.Printf("skip %s %s: schema marshal failed: %v", methodU, path, err)
				continue
			}

			descriptor := opDescriptor{method: methodU, path: path, params: params}
			server.AddTool(&mcp.Tool{
				Name:        name,
				Description: desc,
				InputSchema: json.RawMessage(schemaBytes),
			}, makeHandler(cfg, descriptor))
			count++
		}
	}
	return count
}

func toolNameFor(op map[string]any, method, path string) string {
	raw, _ := op["operationId"].(string)
	if raw == "" {
		raw = fmt.Sprintf("%s_%s", method, path)
	}
	return sanitizeName(raw)
}

func toolDescFor(op map[string]any, methodU, path string) string {
	desc, _ := op["summary"].(string)
	if desc == "" {
		desc, _ = op["description"].(string)
	}
	if desc == "" {
		desc = fmt.Sprintf("%s %s", methodU, path)
	}
	desc = strings.TrimSpace(desc)
	if len(desc) > 1024 {
		desc = desc[:1024]
	}
	return desc
}

func buildSchema(op, spec map[string]any, methodU, path string) (map[string]any, []string, []map[string]any) {
	properties := map[string]any{}
	required := []string{}
	var params []map[string]any

	paramsAny, _ := op["parameters"].([]any)
	for _, p := range paramsAny {
		param, ok := p.(map[string]any)
		if !ok {
			continue
		}
		params = append(params, param)
		pname, _ := param["name"].(string)
		loc, _ := param["in"].(string)

		if loc == "body" {
			body := resolveBodySchema(param, spec)
			if _, has := body["description"]; !has {
				body["description"] = fmt.Sprintf("Request body for %s %s", methodU, path)
			}
			properties[pname] = body
		} else {
			pType, _ := param["type"].(string)
			paramDesc, _ := param["description"].(string)
			if paramDesc == "" {
				paramDesc = fmt.Sprintf("%s parameter", loc)
			}
			properties[pname] = map[string]any{
				"type":        openapiToJSON(pType),
				"description": strings.TrimSpace(paramDesc),
			}
		}

		if req, _ := param["required"].(bool); req {
			required = append(required, pname)
		}
	}
	return properties, required, params
}

// makeHandler returns a ToolHandler that executes a single Vikunja API call
// using the supplied operation descriptor.
func makeHandler(cfg *config, op opDescriptor) mcp.ToolHandler {
	return func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args := map[string]any{}
		if len(req.Params.Arguments) > 0 {
			_ = json.Unmarshal(req.Params.Arguments, &args)
		}

		path := op.path
		query := map[string]string{}
		var body any

		for _, param := range op.params {
			pname, _ := param["name"].(string)
			val, ok := args[pname]
			if !ok || val == nil {
				continue
			}
			switch loc, _ := param["in"].(string); loc {
			case "path":
				path = strings.ReplaceAll(path, "{"+pname+"}", fmt.Sprintf("%v", val))
			case "query":
				query[pname] = fmt.Sprintf("%v", val)
			case "body":
				body = val
			}
		}

		if matches := pathParamRe.FindAllStringSubmatch(path, -1); len(matches) > 0 {
			missing := make([]string, 0, len(matches))
			for _, m := range matches {
				missing = append(missing, m[1])
			}
			msg := "error: missing required path parameters: " + strings.Join(missing, ", ")
			log.Printf("%s %s -> %s", op.method, op.path, msg)
			return toolErr(msg), nil
		}

		var reqBody io.Reader
		if body != nil {
			b, err := json.Marshal(body)
			if err != nil {
				return toolErr("error: failed to marshal body: " + err.Error()), nil
			}
			reqBody = bytes.NewReader(b)
		}

		httpReq, err := http.NewRequestWithContext(ctx, op.method, cfg.baseURL+path, reqBody)
		if err != nil {
			return toolErr("error: " + err.Error()), nil
		}

		if len(query) > 0 {
			q := httpReq.URL.Query()
			for k, v := range query {
				q.Set(k, v)
			}
			httpReq.URL.RawQuery = q.Encode()
		}

		httpReq.Header.Set("Authorization", "Bearer "+cfg.token)
		httpReq.Header.Set("Accept", "application/json")
		if body != nil {
			httpReq.Header.Set("Content-Type", "application/json")
		}

		resp, err := cfg.httpClient.Do(httpReq)
		if err != nil {
			return toolErr("error: " + err.Error()), nil
		}
		defer resp.Body.Close()

		respBytes, _ := io.ReadAll(resp.Body)
		if resp.StatusCode >= 400 {
			log.Printf("%s %s -> HTTP %d", op.method, path, resp.StatusCode)
		}

		text := fmt.Sprintf("HTTP %d\n%s", resp.StatusCode, string(respBytes))
		return &mcp.CallToolResult{
			Content: []mcp.Content{&mcp.TextContent{Text: text}},
		}, nil
	}
}

func toolErr(msg string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: msg}},
		IsError: true,
	}
}
