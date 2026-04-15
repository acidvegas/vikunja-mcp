// Vikunja MCP - Developed by acidvegas in Go (https://git.acid.vegas)
// vikunja-mcp/allowlist.go

package main

type methodPath struct {
	method string
	path   string
}

// Curated allowlist of endpoints the MCP exposes. Anything not in this set is
// dropped at build time. Keeps the tool surface small, predictable, and safe.
var allowlist = map[methodPath]bool{
	// server / user
	{"GET", "/info"}:  true,
	{"GET", "/user"}:  true,
	{"GET", "/users"}: true,
	// projects
	{"GET", "/projects"}:                       true,
	{"PUT", "/projects"}:                       true,
	{"GET", "/projects/{id}"}:                  true,
	{"POST", "/projects/{id}"}:                 true,
	{"DELETE", "/projects/{id}"}:               true,
	{"PUT", "/projects/{projectID}/duplicate"}: true,
	{"GET", "/projects/{id}/projectusers"}:     true,
	// views
	{"GET", "/projects/{project}/views"}:         true,
	{"PUT", "/projects/{project}/views"}:         true,
	{"GET", "/projects/{project}/views/{id}"}:    true,
	{"POST", "/projects/{project}/views/{id}"}:   true,
	{"DELETE", "/projects/{project}/views/{id}"}: true,
	// buckets
	{"GET", "/projects/{id}/views/{view}/buckets"}:                          true,
	{"PUT", "/projects/{id}/views/{view}/buckets"}:                          true,
	{"POST", "/projects/{projectID}/views/{view}/buckets/{bucketID}"}:       true,
	{"DELETE", "/projects/{projectID}/views/{view}/buckets/{bucketID}"}:     true,
	// tasks
	{"GET", "/tasks"}:                                                  true,
	{"GET", "/tasks/{id}"}:                                             true,
	{"POST", "/tasks/{id}"}:                                            true,
	{"DELETE", "/tasks/{id}"}:                                          true,
	{"PUT", "/projects/{id}/tasks"}:                                    true,
	{"POST", "/tasks/bulk"}:                                            true,
	{"POST", "/tasks/{id}/position"}:                                   true,
	{"POST", "/tasks/{projecttask}/read"}:                              true,
	{"GET", "/projects/{id}/views/{view}/tasks"}:                       true,
	{"POST", "/projects/{project}/views/{view}/buckets/{bucket}/tasks"}: true,
	// task relations
	{"PUT", "/tasks/{taskID}/relations"}:                                    true,
	{"DELETE", "/tasks/{taskID}/relations/{relationKind}/{otherTaskID}"}:    true,
	// assignees
	{"GET", "/tasks/{taskID}/assignees"}:                   true,
	{"PUT", "/tasks/{taskID}/assignees"}:                   true,
	{"POST", "/tasks/{taskID}/assignees/bulk"}:             true,
	{"DELETE", "/tasks/{taskID}/assignees/{userID}"}:       true,
	// labels
	{"GET", "/labels"}:                            true,
	{"PUT", "/labels"}:                            true,
	{"GET", "/labels/{id}"}:                       true,
	{"POST", "/labels/{id}"}:                      true,
	{"DELETE", "/labels/{id}"}:                    true,
	{"GET", "/tasks/{task}/labels"}:               true,
	{"PUT", "/tasks/{task}/labels"}:               true,
	{"DELETE", "/tasks/{task}/labels/{label}"}:    true,
	{"POST", "/tasks/{taskID}/labels/bulk"}:       true,
	// comments
	{"GET", "/tasks/{taskID}/comments"}:                  true,
	{"GET", "/tasks/{taskID}/comments/{commentID}"}:      true,
	{"PUT", "/tasks/{taskID}/comments"}:                  true,
	{"POST", "/tasks/{taskID}/comments/{commentID}"}:     true,
	{"DELETE", "/tasks/{taskID}/comments/{commentID}"}:   true,
	// attachments
	{"GET", "/tasks/{id}/attachments"}:                       true,
	{"GET", "/tasks/{id}/attachments/{attachmentID}"}:        true,
	{"PUT", "/tasks/{id}/attachments"}:                       true,
	{"DELETE", "/tasks/{id}/attachments/{attachmentID}"}:     true,
	// reactions
	{"GET", "/{kind}/{id}/reactions"}:         true,
	{"PUT", "/{kind}/{id}/reactions"}:         true,
	{"POST", "/{kind}/{id}/reactions/delete"}: true,
	// filters
	{"PUT", "/filters"}:         true,
	{"GET", "/filters/{id}"}:    true,
	{"POST", "/filters/{id}"}:   true,
	{"DELETE", "/filters/{id}"}: true,
	// teams
	{"GET", "/teams"}:                                  true,
	{"PUT", "/teams"}:                                  true,
	{"GET", "/teams/{id}"}:                             true,
	{"POST", "/teams/{id}"}:                            true,
	{"DELETE", "/teams/{id}"}:                          true,
	{"PUT", "/teams/{id}/members"}:                     true,
	{"POST", "/teams/{id}/members/{userID}/admin"}:     true,
	{"DELETE", "/teams/{id}/members/{username}"}:       true,
	// sharing
	{"GET", "/projects/{id}/users"}:                       true,
	{"PUT", "/projects/{id}/users"}:                       true,
	{"POST", "/projects/{projectID}/users/{userID}"}:      true,
	{"DELETE", "/projects/{projectID}/users/{userID}"}:    true,
	{"GET", "/projects/{id}/teams"}:                       true,
	{"PUT", "/projects/{id}/teams"}:                       true,
	{"POST", "/projects/{projectID}/teams/{teamID}"}:      true,
	{"DELETE", "/projects/{projectID}/teams/{teamID}"}:    true,
	// link shares
	{"GET", "/projects/{project}/shares"}:             true,
	{"GET", "/projects/{project}/shares/{share}"}:     true,
	{"PUT", "/projects/{project}/shares"}:             true,
	{"DELETE", "/projects/{project}/shares/{share}"}:  true,
	// subscriptions / notifications
	{"PUT", "/subscriptions/{entity}/{entityID}"}:    true,
	{"DELETE", "/subscriptions/{entity}/{entityID}"}: true,
	{"GET", "/notifications"}:                        true,
	{"POST", "/notifications"}:                       true,
	{"POST", "/notifications/{id}"}:                  true,
	// webhooks
	{"GET", "/projects/{id}/webhooks"}:                true,
	{"PUT", "/projects/{id}/webhooks"}:                true,
	{"POST", "/projects/{id}/webhooks/{webhookID}"}:   true,
	{"DELETE", "/projects/{id}/webhooks/{webhookID}"}: true,
	{"GET", "/webhooks/events"}:                       true,
}

func isAllowlisted(method, path string) bool {
	return allowlist[methodPath{method, path}]
}
