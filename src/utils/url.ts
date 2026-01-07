/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */


export function mergeUrlParts(baseUrl: string, suffix: string): string {
  const trimmedBaseUrl = baseUrl.replace(/\/+$/, '');
  const trimmedSuffix = suffix.replace(/^\/+/, '');
  
  return `${trimmedBaseUrl}/${trimmedSuffix}`;
}
