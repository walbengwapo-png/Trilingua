// Offline converter probe. The output is inspected as text, never executed.
const fs = require('node:fs');
const { createRequire } = require('node:module');
const assert = require('node:assert/strict');
const appRequire = createRequire(process.argv[2] + '/package.json');
const mammoth = appRequire('mammoth/mammoth.browser');
const bytes = fs.readFileSync(process.argv[3]);
const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
mammoth.convertToHtml({ arrayBuffer }).then(({ value }) => {
  assert(value.includes('href="javascript:void(0)"'));
  const result = { javascript_uri_retained: true, html: value, browser_execution_tested: false };
  fs.writeFileSync(process.argv[4], JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
}).catch(error => { console.error(error); process.exitCode = 1; });
