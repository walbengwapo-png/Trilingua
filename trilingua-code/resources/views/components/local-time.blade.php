@props(['value'])
@php($date = \Carbon\Carbon::parse($value)->utc())
<time datetime="{{ $date->toIso8601String() }}" data-local-time>{{ $date->format('j M Y, g:i A') }} UTC</time>
