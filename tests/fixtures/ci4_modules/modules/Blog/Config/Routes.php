<?php
$routes->group('backend/blogs', ['namespace' => 'Modules\Blog\Controllers'], function ($routes) {
    $routes->match(['GET', 'POST'], '/', 'Blog::index');
    $routes->post('delete', 'Blog::delete');
    $routes->group('tags', function ($routes) {
        $routes->get('/', 'Tags::index');
    });
});
