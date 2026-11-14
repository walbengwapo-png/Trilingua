import test from 'node:test';
import {readFileSync} from 'node:fs';
import {Script} from 'node:vm';

// Vite does not parse scripts embedded in Blade templates. Parse those as well.
for (const name of ['layouts/app', 'translation', 'history', 'history-detail', 'bookmarks',
    'my-documents', 'notifications', 'admin/review-document', 'admin/review-text']) {
    test(`${name} inline scripts parse`, () => {
        const template = readFileSync(new URL(`../../resources/views/${name}.blade.php`, import.meta.url), 'utf8');
        for (const match of template.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
            const javascript = match[1].replace(/@json\([^;\n]*\)/g, 'null')
                .replace(/{{[\s\S]*?}}/g, 'fixture');
            new Script(javascript, {filename: `${name}.blade.php`});
        }
    });
}
