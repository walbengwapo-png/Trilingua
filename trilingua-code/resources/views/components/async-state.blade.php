@props([
    'state' => 'empty', // loading|empty|error
    'message' => '',
    'retryUrl' => null,
])

<div class="ui-state ui-state--{{ $state }}" role="{{ $state === 'error' ? 'alert' : 'status' }}" @if($state === 'loading') aria-live="polite" @endif>
    <p>{{ $message }}</p>
    @if ($retryUrl)
        <a class="btn secondary" href="{{ $retryUrl }}">Try again</a>
    @endif
</div>
