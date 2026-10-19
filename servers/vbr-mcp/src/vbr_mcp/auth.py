# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import secrets

from fastmcp.server.auth import AccessToken, TokenVerifier


class StaticBearerVerifier(TokenVerifier):
    def __init__(self, tokens: dict[str, str]) -> None:
        super().__init__()
        self._tokens = tokens

    async def verify_token(self, token: str) -> AccessToken | None:
        matched_client: str | None = None
        for configured_token, client_name in self._tokens.items():
            if secrets.compare_digest(token, configured_token):
                matched_client = client_name
        if matched_client is None:
            return None
        return AccessToken(token=token, client_id=matched_client, scopes=[])
