package com.naivefirst.morenaive

import org.springframework.http.HttpStatus
import org.springframework.http.converter.HttpMessageNotReadableException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException

@RestControllerAdvice
class TestApiErrors {
    @ExceptionHandler(InvalidTestRequestException::class, HttpMessageNotReadableException::class, MethodArgumentTypeMismatchException::class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    fun badRequest(): Map<String, String> = mapOf("message" to "Invalid request")

    @ExceptionHandler(TestRecordNotFoundException::class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    fun notFound(): Map<String, String> = mapOf("message" to "Test record not found")
}
