<?php

namespace App\Exceptions;

use RuntimeException;

/**
 * Thrown when an admin review write is based on a stale draft revision or a
 * stale file pointer. The request must NOT overwrite newer draft text; callers
 * translate this into an HTTP 409 so the client reloads the latest state.
 */
class ReviewConflictException extends RuntimeException
{
}
