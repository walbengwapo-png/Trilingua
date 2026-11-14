@include('errors.notice', ['notice' => \App\Support\UserMessages::get('server_error'), 'status' => 500, 'reference' => \App\Support\WebErrorResponse::reference(request())])
