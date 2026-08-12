@if ($paginator->hasPages())
    <nav role="navigation" aria-label="{{ __('Pagination Navigation') }}" class="pg">
        <div class="pg__inner">

            {{-- Previous Page Link --}}
            @if ($paginator->onFirstPage())
                <span class="pg-btn" aria-disabled="true" aria-label="{{ __('pagination.previous') }}">
                    <span class="pg-arrow" aria-hidden="true">&larr;</span>
                    <span>Previous</span>
                </span>
            @else
                <a href="{{ $paginator->previousPageUrl() }}" rel="prev" class="pg-btn" aria-label="{{ __('pagination.previous') }}">
                    <span class="pg-arrow" aria-hidden="true">&larr;</span>
                    <span>Previous</span>
                </a>
            @endif

            {{-- Pagination Elements --}}
            <div class="pg__pages">
                @foreach ($elements as $element)
                    {{-- "Three Dots" Separator --}}
                    @if (is_string($element))
                        <span class="pg-num pg-num--dots" aria-disabled="true">{{ $element }}</span>
                    @endif

                    {{-- Array Of Links --}}
                    @if (is_array($element))
                        @foreach ($element as $page => $url)
                            @if ($page == $paginator->currentPage())
                                <span class="pg-num is-active" aria-current="page">{{ $page }}</span>
                            @else
                                <a class="pg-num" href="{{ $url }}" aria-label="{{ __('Go to page :page', ['page' => $page]) }}">{{ $page }}</a>
                            @endif
                        @endforeach
                    @endif
                @endforeach
            </div>

            {{-- Next Page Link --}}
            @if ($paginator->hasMorePages())
                <a href="{{ $paginator->nextPageUrl() }}" rel="next" class="pg-btn" aria-label="{{ __('pagination.next') }}">
                    <span>Next</span>
                    <span class="pg-arrow" aria-hidden="true">&rarr;</span>
                </a>
            @else
                <span class="pg-btn" aria-disabled="true" aria-label="{{ __('pagination.next') }}">
                    <span>Next</span>
                    <span class="pg-arrow" aria-hidden="true">&rarr;</span>
                </span>
            @endif

        </div>
    </nav>
@endif