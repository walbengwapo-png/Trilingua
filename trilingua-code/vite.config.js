import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
    plugins: [
        laravel({
            input: [
                'resources/css/base.css',
                'resources/css/layouts/app.css',
                'resources/css/layouts/guest.css',
                'resources/css/views/auth/login.css',
                'resources/css/views/auth/register.css',
                'resources/css/views/dashboard.css',
                'resources/css/views/settings.css',
                'resources/css/views/history.css',
                'resources/css/views/my-documents.css',
                'resources/css/views/translation.css',
                'resources/css/views/welcome.css',
                'resources/css/views/admin.css',
                'resources/js/app.js',
                'resources/js/review-document.js'
            ],
            refresh: true,
        }),
        tailwindcss(),
    ],
    server: {
        watch: {
            ignored: ['**/storage/framework/views/**'],
        },
    },
});
