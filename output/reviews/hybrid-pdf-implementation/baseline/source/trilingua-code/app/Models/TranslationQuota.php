<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class TranslationQuota extends Model
{
    protected $table = 'translation_quota';

    protected $guarded = [];

    protected $casts = [
        'files' => 'integer',
        'bytes' => 'integer',
        'quota_day' => 'date:Y-m-d',
    ];
}