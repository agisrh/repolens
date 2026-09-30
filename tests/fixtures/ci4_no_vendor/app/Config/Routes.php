<?php
$routes->setDefaultController('Home');
$routes->setAutoRoute(env('AUTO_ROUTE', false));
$routes->get('/', 'Home::index');
$routes->get('berita/(:segment)', 'Berita::detail/$1');
$routes->group('admin', function ($routes) {
    $routes->get('dashboard', 'Admin\\Dashboard::index');
    $routes->post('berita/simpan', 'Admin\\Dashboard::simpan');
});
$routes->resource('photos');
