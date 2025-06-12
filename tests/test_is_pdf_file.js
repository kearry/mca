import { test } from 'node:test';
import assert from 'node:assert';
import { isPdfFile } from '../src/lib/isPdfFile.js';

test('rejects non-pdf by extension and mime', () => {
  assert.strictEqual(isPdfFile('file.txt', 'text/plain'), false);
});

test('accepts pdf extension', () => {
  assert.strictEqual(isPdfFile('document.pdf', 'application/octet-stream'), true);
});

test('accepts pdf mime', () => {
  assert.strictEqual(isPdfFile('random', 'application/pdf'), true);
});
