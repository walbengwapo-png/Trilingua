<?php

namespace App\Support;

use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Symfony\Component\HttpFoundation\Response;

class WebErrorResponse
{
    public static function respond(Request $request, Response $response): Response
    {
        $status = $response->getStatusCode();
        $code = match ($status) {
            401 => 'sign_in_required', 403 => 'access_denied', 404 => 'page_missing',
            419 => 'session_expired', 429 => 'rate_limited',
            500 => 'server_error', 502, 503, 504 => 'service_unavailable', default => null,
        };
        if ($code === null) {
            return $response;
        }
        $notice = UserMessages::get($code);
        $reference = $status >= 500 ? self::reference($request) : null;
        if ($request->expectsJson()) {
            $result = response()->json(['code' => $code, 'message' => $notice['message'], 'title' => $notice['title'],
                'reference' => $reference], $status);
        } elseif ($status === 419 && $request->isMethod('POST') && $request->is('login')) {
            $result = redirect()->route('login')->with('notice', 'login_form_expired')->withInput($request->only('email'));
        } else {
            $result = response()->view('errors.notice', compact('notice', 'status', 'reference'), $status);
        }
        foreach (['Retry-After', 'WWW-Authenticate'] as $header) {
            if ($response->headers->has($header)) {
                $result->headers->set($header, $response->headers->get($header));
            }
        }
        $result->headers->set('Cache-Control', 'no-store, private');
        return $result;
    }

    public static function reference(Request $request): string
    {
        $reference = $request->attributes->get('support_reference') ?? (string) Str::uuid();
        $request->attributes->set('support_reference', $reference);
        return $reference;
    }
}
