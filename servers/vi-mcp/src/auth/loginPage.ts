/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import type { Response } from 'express';

export interface LoginPageModel {
    productName: string;
    clientName?: string;
    redirectUri?: string;
    request?: string;
    username?: string;
    error?: string;
}

function escapeHtml(value: string): string {
    return value.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
}

export function renderLoginPage(model: LoginPageModel): string {
    const intro =
        model.clientName !== undefined && model.redirectUri !== undefined
            ? `<p class="client"><strong>${escapeHtml(model.clientName)}</strong> asks to use Veeam Intelligence with your account.
      After you sign in you are sent to <strong>${escapeHtml(model.redirectUri)}</strong>. Continue only if you started this from your MCP client.</p>`
            : '';
    const error = model.error !== undefined ? `<p class="error" role="alert">${escapeHtml(model.error)}</p>` : '';
    const form =
        model.request === undefined
            ? ''
            : `<form method="post" action="/login" autocomplete="on">
      <input type="hidden" name="request" value="${escapeHtml(model.request)}">
      <label>User name<input name="username" autocomplete="username" required autofocus value="${escapeHtml(model.username ?? '')}"></label>
      <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">Sign in</button>
    </form>`;

    return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in to ${escapeHtml(model.productName)}</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f4f5f7; color: #1d1d1f; margin: 0; padding: 16px; }
    main { max-width: 380px; margin: 10vh auto; background: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.12); }
    h1 { font-size: 1.25rem; margin: 0 0 12px; }
    p { line-height: 1.4; }
    .client { overflow-wrap: anywhere; font-size: .9rem; color: #444; }
    label { display: block; margin-top: 12px; font-size: .9rem; }
    input:not([type=hidden]) { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px; font-size: 1rem; }
    button { margin-top: 20px; width: 100%; padding: 10px; font-size: 1rem; background: #00b336; color: #fff; border: 0; border-radius: 4px; cursor: pointer; }
    .error { color: #b00020; }
  </style>
</head>
<body>
  <main>
    <h1>Sign in to ${escapeHtml(model.productName)}</h1>
    ${intro}
    ${error}
    ${form}
  </main>
</body>
</html>`;
}

export function sendLoginPage(res: Response, status: number, model: LoginPageModel): void {
    res.status(status)
        .set({
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
            'X-Frame-Options': 'DENY',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'same-origin',
        })
        .send(renderLoginPage(model));
}
