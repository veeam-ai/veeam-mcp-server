# Security Policy

## Reporting a vulnerability

Please do not open a public GitHub issue for security problems.

Report privately through **GitHub's private vulnerability reporting** on this repository
(Security → Report a vulnerability). If you cannot use GitHub, use the disclosure channel
on the [Veeam security page](https://www.veeam.com/security).

Please include the affected version or commit, a description of the issue, the steps to
reproduce it, and the impact you expect. We will acknowledge your report and keep you
updated on remediation and disclosure.

## Supported versions

This project is pre-1.0. Fixes are released against the `main` branch; there are no
maintained release branches yet.

## Security model

Understanding what this server is makes it easier to judge whether a finding is a
vulnerability or expected behavior.

The server holds **VBR administrator credentials** and exposes them as MCP tools. Of its
49 tools, 20 change state and 12 can interrupt protection or overwrite production data —
restores, instant recovery, job control, SOBR extent modes and license revocation. Anyone
who can reach the server can invoke those tools with the privileges of the configured VBR
account, so the server's reachability is the real security boundary.

Specific properties worth knowing:

- **Credentials come only from the environment** (`VBR_USERNAME` / `VBR_PASSWORD`), never
  from source or a committed file, and are never baked into a container layer.
- **The server runs over stdio**, locally and in the container image alike: the MCP client
  spawns it as its own child process. stdio performs no authentication and needs none.
- **`VBR_VERIFY_TLS=False` disables certificate verification** for the connection to VBR.
  It exists for self-signed lab certificates. Do not use it against production: to keep a
  self-signed or private-CA certificate verified, point `SSL_CERT_FILE` at a PEM file with
  the server's certificate or its CA instead.
- **Tool annotations are advisory.** Every tool is annotated `readOnlyHint` /
  `destructiveHint` so a client can prompt before a destructive call, but honoring them is
  the client's choice. They are not an authorization mechanism.

The server does not enforce its own authorization model on top of VBR. Restrict what it can
do by giving it a **least-privilege VBR account** rather than a full administrator.
