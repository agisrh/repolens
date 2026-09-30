<?php
Schema::create('orders', function (Blueprint $table) {
    $table->id();
    $table->foreignId('customer_id')->constrained();
    $table->string('awb', 30)->unique();
    $table->decimal('weight', 8, 2)->nullable();
    $table->timestamps();
});
