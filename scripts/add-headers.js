#!/usr/bin/env node
/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const COPYRIGHT_HEADER = `/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

`;

const extensions = ['.ts', '.js', '.mjs'];
const excludeDirs = ['node_modules', 'build', 'dist', 'coverage', '__tests__'];
const excludeFiles = ['jest.config.js', 'eslint.config.js', 'esbuild.config.js'];

function removeExistingHeader(content) {
  // Preserve shebang if present
  let shebang = '';
  let workingContent = content;
  
  if (content.startsWith('#!')) {
    const firstNewline = content.indexOf('\n');
    shebang = content.substring(0, firstNewline + 1);
    workingContent = content.substring(firstNewline + 1);
  }
  
  let result = workingContent;
  let changed = true;
  
  // Keep removing copyright headers until none are left
  while (changed) {
    changed = false;
    const trimmed = result.trimStart();
    
    if (trimmed.startsWith('/**')) {
      const endOfComment = trimmed.indexOf('*/');
      if (endOfComment !== -1) {
        const commentBlock = trimmed.substring(0, endOfComment + 2);
        
        // Check if this is a copyright/license header
        if (commentBlock.includes('Copyright') || commentBlock.includes('LICENSE') || commentBlock.includes('Licensed')) {
          // Get content after the comment block
          let afterComment = trimmed.substring(endOfComment + 2);
          
          // Remove any extra newlines after the comment
          afterComment = afterComment.replace(/^\n+/, '');
          
          result = afterComment;
          changed = true;
        }
      }
    }
  }
  
  return shebang + result;
}

function hasCorrectHeader(content) {
  const trimmed = content.trimStart();
  
  // Must start with our exact header
  if (!trimmed.startsWith('/**\n * Copyright © Veeam Software Group GmbH.')) {
    return false;
  }
  
  // Check for duplicates - there should be only one /** comment at the start
  const firstEnd = trimmed.indexOf('*/');
  if (firstEnd === -1) return false;
  
  const afterFirst = trimmed.substring(firstEnd + 2).trimStart();
  
  // If there's another /** comment that contains Copyright/License, it's a duplicate
  if (afterFirst.startsWith('/**')) {
    const secondEnd = afterFirst.indexOf('*/');
    if (secondEnd !== -1) {
      const secondBlock = afterFirst.substring(0, secondEnd + 2);
      if (secondBlock.includes('Copyright') || secondBlock.includes('LICENSE') || secondBlock.includes('Licensed')) {
        return false; // Has duplicate header
      }
    }
  }
  
  return trimmed.includes('Copyright © Veeam Software Group GmbH.') &&
         trimmed.includes('Licensed under the MIT License.') &&
         trimmed.includes('See LICENSE in the project root for license information.');
}

function addHeaderToFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  
  if (hasCorrectHeader(content)) {
    console.log(`✓ Already has correct header: ${filePath}`);
    return false;
  }

  // Remove any existing copyright header
  content = removeExistingHeader(content);

  // Handle shebang lines
  let newContent;
  if (content.startsWith('#!')) {
    const firstNewline = content.indexOf('\n');
    const shebang = content.substring(0, firstNewline + 1);
    const rest = content.substring(firstNewline + 1);
    newContent = shebang + COPYRIGHT_HEADER + rest;
  } else {
    newContent = COPYRIGHT_HEADER + content;
  }

  fs.writeFileSync(filePath, newContent, 'utf8');
  console.log(`✓ Updated header: ${filePath}`);
  return true;
}

function walkDir(dir) {
  let count = 0;
  const files = fs.readdirSync(dir);

  for (const file of files) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);

    if (stat.isDirectory()) {
      if (!excludeDirs.includes(file) && !file.startsWith('.')) {
        count += walkDir(filePath);
      }
    } else if (stat.isFile()) {
      const ext = path.extname(file);
      if (extensions.includes(ext) && !excludeFiles.includes(file)) {
        if (addHeaderToFile(filePath)) {
          count++;
        }
      }
    }
  }

  return count;
}

const projectRoot = path.resolve(__dirname, '..');
console.log('Adding copyright headers to all source files...\n');

const count = walkDir(projectRoot);

console.log(`\n✓ Done! Added headers to ${count} file(s).`);
