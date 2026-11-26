package com.naivefirst.morenaive

import io.swagger.v3.oas.annotations.media.Schema
import org.springframework.http.HttpStatus
import org.springframework.http.converter.HttpMessageNotReadableException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException

@Schema(description = "오류 응답")
data class TestApiErrorResponse(
    @field:Schema(description = "오류 사유. 내부 예외와 접속 정보는 담지 않습니다.", example = "Invalid request", requiredMode = Schema.RequiredMode.REQUIRED)
    val message: String,
)

@RestControllerAdvice
class TestApiErrors {
    @ExceptionHandler(InvalidTestRequestException::class, HttpMessageNotReadableException::class, MethodArgumentTypeMismatchException::class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    fun badRequest(): TestApiErrorResponse = TestApiErrorResponse("Invalid request")

    @ExceptionHandler(TestRecordNotFoundException::class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    fun notFound(): TestApiErrorResponse = TestApiErrorResponse("Test record not found")
}
