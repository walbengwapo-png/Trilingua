<?php

namespace App\Support;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;

class LoginDestination
{
    public static function take(Request $request): string
    {
        $fallback = route('dashboard');
        $target = $request->session()->pull('url.intended');
        if (!is_string($target) || preg_match('/[\\\\\x00-\x20]/', $target)) {
            return $fallback;
        }
        if (str_starts_with($target, '/') && !str_starts_with($target, '//')) {
            $target = $request->getSchemeAndHttpHost().$target;
        }
        $parts = parse_url($target);
        $origin = parse_url($fallback);
        if (!$parts || !isset($parts['host']) || (isset($parts['user']) || isset($parts['pass']))
            || ($parts['scheme'] ?? '') !== ($origin['scheme'] ?? '')
            || strtolower($parts['host']) !== strtolower($origin['host'])
            || ($parts['port'] ?? null) !== ($origin['port'] ?? null)) {
            return $fallback;
        }
        try {
            $route = Route::getRoutes()->match(Request::create($target, 'GET'));
            $allowed = ['dashboard', 'translate', 'history', 'history.view', 'documents', 'bookmarks',
                'notifications.page', 'profile', 'settings'];
            if ($request->user()?->is_admin) {
                $allowed = array_merge($allowed, ['admin.dashboard', 'admin.review.index', 'admin.review.show',
                    'admin.audit', 'admin.jobs.index', 'admin.users.index', 'admin.users.show']);
            }
            return in_array($route->getName(), $allowed, true) ? $target : $fallback;
        } catch (\Symfony\Component\HttpKernel\Exception\HttpExceptionInterface) {
            return $fallback;
        }
    }
}
