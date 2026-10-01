@tool
extends RefCounted
## Keep in sync with docs/EDITOR_API.json inputSchema; validated inside editor.
const SCHEMAS := {
	"status": {
		"type": "object",
		"properties": {},
		"required": [],
		"additionalProperties": false
	},
	"hierarchy": {
		"type": "object",
		"properties": {
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"max_depth": {
				"type": "integer",
				"minimum": 0,
				"maximum": 32
			}
		},
		"required": [],
		"additionalProperties": false
	},
	"node_inspect": {
		"type": "object",
		"properties": {
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			}
		},
		"required": [
			"node_path"
		],
		"additionalProperties": false
	},
	"scene_create": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			},
			"root_type": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"root_name": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"path",
			"root_type",
			"root_name"
		],
		"additionalProperties": false
	},
	"scene_open": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"path"
		],
		"additionalProperties": false
	},
	"scene_save": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"expected_disk_sha256": {
				"type": "string",
				"maxLength": 64,
				"description": "scene.disk_sha256 from a fresh status, or empty only for an absent destination.",
				"pattern": "^([0-9a-f]{64})?$"
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"expected_disk_sha256"
		],
		"additionalProperties": false
	},
	"node_create": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"parent_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_parent_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"type": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"name": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"parent_path",
			"expected_parent_id",
			"type",
			"name"
		],
		"additionalProperties": false
	},
	"node_delete": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id"
		],
		"additionalProperties": false
	},
	"node_duplicate": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"name": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"name"
		],
		"additionalProperties": false
	},
	"node_reparent": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"new_parent_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_new_parent_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"keep_global_transform": {
				"type": "boolean"
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"new_parent_path",
			"expected_new_parent_id"
		],
		"additionalProperties": false
	},
	"node_rename": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"name": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"name"
		],
		"additionalProperties": false
	},
	"property_set": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"property": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"value": {
				"anyOf": [
					{
						"type": "null"
					},
					{
						"type": "boolean"
					},
					{
						"type": "number"
					},
					{
						"type": "string",
						"maxLength": 4096
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "Vector2"
							},
							"x": {
								"type": "number"
							},
							"y": {
								"type": "number"
							}
						},
						"required": [
							"type",
							"x",
							"y"
						],
						"additionalProperties": false
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "Vector3"
							},
							"x": {
								"type": "number"
							},
							"y": {
								"type": "number"
							},
							"z": {
								"type": "number"
							}
						},
						"required": [
							"type",
							"x",
							"y",
							"z"
						],
						"additionalProperties": false
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "Vector2i"
							},
							"x": {
								"type": "integer",
								"minimum": -2147483648,
								"maximum": 2147483647
							},
							"y": {
								"type": "integer",
								"minimum": -2147483648,
								"maximum": 2147483647
							}
						},
						"required": [
							"type",
							"x",
							"y"
						],
						"additionalProperties": false
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "Vector3i"
							},
							"x": {
								"type": "integer",
								"minimum": -2147483648,
								"maximum": 2147483647
							},
							"y": {
								"type": "integer",
								"minimum": -2147483648,
								"maximum": 2147483647
							},
							"z": {
								"type": "integer",
								"minimum": -2147483648,
								"maximum": 2147483647
							}
						},
						"required": [
							"type",
							"x",
							"y",
							"z"
						],
						"additionalProperties": false
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "Color"
							},
							"r": {
								"type": "number"
							},
							"g": {
								"type": "number"
							},
							"b": {
								"type": "number"
							},
							"a": {
								"type": "number"
							}
						},
						"required": [
							"type",
							"r",
							"g",
							"b",
							"a"
						],
						"additionalProperties": false
					},
					{
						"type": "object",
						"properties": {
							"type": {
								"const": "NodePath"
							},
							"value": {
								"type": "string",
								"maxLength": 4096,
								"description": "NodePath property relative to its target node. Empty clears it; parent segments are allowed only when addon resolution stays within the edited scene."
							}
						},
						"required": [
							"type",
							"value"
						],
						"additionalProperties": false
					}
				]
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"property",
			"value"
		],
		"additionalProperties": false
	},
	"signal_connect": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"signal": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"target_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_target_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"method": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"signal",
			"target_path",
			"expected_target_id",
			"method"
		],
		"additionalProperties": false
	},
	"signal_disconnect": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"signal": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"target_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_target_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"method": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"signal",
			"target_path",
			"expected_target_id",
			"method"
		],
		"additionalProperties": false
	},
	"script_attach": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"script_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"script_path"
		],
		"additionalProperties": false
	},
	"script_read": {
		"type": "object",
		"properties": {
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			}
		},
		"required": [
			"path"
		],
		"additionalProperties": false
	},
	"script_write": {
		"type": "object",
		"properties": {
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			},
			"source": {
				"type": "string",
				"maxLength": 1048576
			},
			"overwrite": {
				"type": "boolean"
			},
			"expected_sha256": {
				"type": "string",
				"maxLength": 64,
				"pattern": "^[0-9a-f]{64}$"
			}
		},
		"required": [
			"path",
			"source"
		],
		"additionalProperties": false
	},
	"resource_create": {
		"type": "object",
		"properties": {
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			},
			"type": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"properties": {
				"type": "object",
				"additionalProperties": {
					"anyOf": [
						{
							"type": "null"
						},
						{
							"type": "boolean"
						},
						{
							"type": "number"
						},
						{
							"type": "string",
							"maxLength": 4096
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "Vector2"
								},
								"x": {
									"type": "number"
								},
								"y": {
									"type": "number"
								}
							},
							"required": [
								"type",
								"x",
								"y"
							],
							"additionalProperties": false
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "Vector3"
								},
								"x": {
									"type": "number"
								},
								"y": {
									"type": "number"
								},
								"z": {
									"type": "number"
								}
							},
							"required": [
								"type",
								"x",
								"y",
								"z"
							],
							"additionalProperties": false
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "Vector2i"
								},
								"x": {
									"type": "integer",
									"minimum": -2147483648,
									"maximum": 2147483647
								},
								"y": {
									"type": "integer",
									"minimum": -2147483648,
									"maximum": 2147483647
								}
							},
							"required": [
								"type",
								"x",
								"y"
							],
							"additionalProperties": false
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "Vector3i"
								},
								"x": {
									"type": "integer",
									"minimum": -2147483648,
									"maximum": 2147483647
								},
								"y": {
									"type": "integer",
									"minimum": -2147483648,
									"maximum": 2147483647
								},
								"z": {
									"type": "integer",
									"minimum": -2147483648,
									"maximum": 2147483647
								}
							},
							"required": [
								"type",
								"x",
								"y",
								"z"
							],
							"additionalProperties": false
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "Color"
								},
								"r": {
									"type": "number"
								},
								"g": {
									"type": "number"
								},
								"b": {
									"type": "number"
								},
								"a": {
									"type": "number"
								}
							},
							"required": [
								"type",
								"r",
								"g",
								"b",
								"a"
							],
							"additionalProperties": false
						},
						{
							"type": "object",
							"properties": {
								"type": {
									"const": "NodePath"
								},
								"value": {
									"type": "string",
									"maxLength": 4096,
									"description": "NodePath property relative to its target node. Empty clears it; parent segments are allowed only when addon resolution stays within the edited scene."
								}
							},
							"required": [
								"type",
								"value"
							],
							"additionalProperties": false
						}
					]
				},
				"maxProperties": 64
			}
		},
		"required": [
			"path",
			"type"
		],
		"additionalProperties": false
	},
	"resource_assign": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"node_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Root-relative node path, '.' for the scene root. No absolute paths or '..'.",
				"minLength": 1
			},
			"expected_node_id": {
				"type": "string",
				"maxLength": 32,
				"description": "Exact node_id from a fresh hierarchy or node_inspect result.",
				"pattern": "^[0-9]+$",
				"minLength": 1
			},
			"property": {
				"type": "string",
				"maxLength": 128,
				"minLength": 1
			},
			"resource_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"node_path",
			"expected_node_id",
			"property",
			"resource_path"
		],
		"additionalProperties": false
	},
	"editor_undo": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision"
		],
		"additionalProperties": false
	},
	"editor_redo": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision"
		],
		"additionalProperties": false
	},
	"play_current": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision"
		],
		"additionalProperties": false
	},
	"play_main": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision"
		],
		"additionalProperties": false
	},
	"play_custom": {
		"type": "object",
		"properties": {
			"expected_scene_path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Exact scene.path from a fresh status; empty for no/unsaved scene."
			},
			"expected_revision": {
				"type": "string",
				"maxLength": 4096,
				"description": "Opaque scene.revision from a fresh status. Never synthesize this value.",
				"minLength": 1
			},
			"path": {
				"type": "string",
				"maxLength": 4096,
				"description": "Project-local res:// path; no traversal, symlinks, generated files or absolute paths.",
				"minLength": 7
			}
		},
		"required": [
			"expected_scene_path",
			"expected_revision",
			"path"
		],
		"additionalProperties": false
	},
	"stop": {
		"type": "object",
		"properties": {},
		"required": [],
		"additionalProperties": false
	},
	"diagnostics": {
		"type": "object",
		"properties": {
			"limit": {
				"type": "integer",
				"minimum": 1,
				"maximum": 200
			}
		},
		"required": [],
		"additionalProperties": false
	}
}
