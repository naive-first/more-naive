package com.naivefirst.morenaive

import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

data class TestResponse(val id: Long, val value: String)

@RestController
@RequestMapping("/api/tests")
class TestController(private val service: TestRecordService) {
    @PostMapping
    fun create(@RequestBody request: TestWriteRequest): ResponseEntity<TestResponse> {
        val record = service.create(request.requireValue())
        return ResponseEntity.status(HttpStatus.CREATED).body(TestResponse(record.id!!, record.value))
    }
}
