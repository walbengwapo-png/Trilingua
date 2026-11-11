<?php

namespace App\Database;

use Illuminate\Database\Connectors\ConnectionFactory;

class PostgresConnection extends \Illuminate\Database\PostgresConnection
{
    /**
     * Prepare bindings so PostgreSQL receives native boolean literals for
     * PHP booleans instead of integers (which PG rejects for boolean columns).
     */
    public function prepareBindings(array $bindings): array
    {
        foreach ($bindings as $key => $value) {
            if (is_bool($value)) {
                $bindings[$key] = $value ? 'true' : 'false';
            }
        }

        return parent::prepareBindings($bindings);
    }
}