<?php
use App\Http\Controllers\OrderController;
Route::prefix('v1')->middleware('auth:sanctum')->group(function () {
    Route::get('/orders/{order}/track', [OrderController::class, 'track']);
    Route::apiResource('orders', OrderController::class);
});
Route::post('/login', [AuthController::class, 'login']);
