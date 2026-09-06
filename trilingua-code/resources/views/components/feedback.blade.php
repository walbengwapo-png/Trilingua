@props(['type' => 'success', 'message' => ''])

<div class="ui-feedback ui-feedback--{{ $type }}" role="status" aria-live="polite">{{ $message }}</div>
