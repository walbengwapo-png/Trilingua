<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class StorageCleanupOutbox extends Model
{
    public const STATUS_PENDING = 'pending';
    public const STATUS_DONE = 'done';

    protected $table = 'storage_cleanup_outbox';

    protected $guarded = [];

    protected $casts = [
        'attempts' => 'integer',
    ];
}