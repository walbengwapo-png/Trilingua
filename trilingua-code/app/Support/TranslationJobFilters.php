<?php

namespace App\Support;

use App\Models\TranslationJob;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

final class TranslationJobFilters
{
    public static function validated(Request $request): array
    {
        $request->validate(['status' => ['nullable', 'string', Rule::in([
            ...TranslationJob::ACTIVE_STATUSES, ...TranslationJob::TERMINAL_STATUSES,
        ])], 'q' => ['nullable', 'string', 'max:200']]);
        return ['status' => trim((string) $request->input('status', '')),
            'q' => trim((string) $request->input('q', ''))];
    }

    public static function apply(Builder $query, array $filters): Builder
    {
        return $query->when($filters['status'] !== '', fn ($q) => $q->where('status', $filters['status']))
            ->when($filters['q'] !== '', fn ($q) => $q->where(function ($inner) use ($filters): void {
                $search = '%'.$filters['q'].'%';
                $inner->where('original_name', 'like', $search)->orWhere('uuid', 'like', $search);
            }));
    }
}
