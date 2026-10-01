<?php
// Every module brings its own Config/Routes.php, loaded here.
foreach (scandir(ROOTPATH . 'modules/') as $module) {
    $routesPath = ROOTPATH . 'modules/' . $module . '/Config/Routes.php';
    if (is_file($routesPath)) require($routesPath);
}
require APPPATH . 'Config/templates/default/Routes.php';

$routes->get('/', 'Home::index', ['as' => 'home']);
