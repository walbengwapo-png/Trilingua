@props(['code' => null, 'type' => 'info', 'title' => null, 'message' => null])
@php
    $entry = $code ? \App\Support\UserMessages::get($code) : [];
    $type = $entry['type'] ?? $type;
    $title = $entry['title'] ?? $title;
    $message = $entry['message'] ?? ($message ? \App\Support\UserMessages::readable($message) : null);
@endphp
<div {{ $attributes->class(['app-notice', 'app-notice--'.$type]) }} role="{{ in_array($type, ['error','warning']) ? 'alert' : 'status' }}">
    <span class="app-notice__icon" aria-hidden="true">{{ $type === 'success' ? '✓' : ($type === 'info' ? 'i' : '!') }}</span>
    <div class="app-notice__body">
        @if ($title)<strong>{{ $title }}</strong>@endif
        @if ($message)<p>{{ $message }}</p>@endif
        {{ $slot }}
    </div>
</div>
