# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Typed request-body parts of VBR endpoints, so tools publish their real schema to MCP clients.

One module per tool (named after the endpoint it feeds), plus `shared` for parts several tools use. Each model mirrors
the VBR REST API 1.3-rev2 schema of the same name. Fields keep VBR's camelCase so bodies serialize without aliases,
and `extra="forbid"` makes a misspelled field fail validation instead of being silently dropped.
"""
