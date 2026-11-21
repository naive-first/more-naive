package com.naivefirst.morenaive

import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.ResponseStatus
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
        return ResponseEntity.status(HttpStatus.CREATED).body(response(record))
    }

    @GetMapping
    fun list(): List<TestResponse> = service.list().map(::response)

    @GetMapping("/{id}")
    fun get(@PathVariable id: Long): TestResponse = response(service.get(requireId(id)))

    @PutMapping("/{id}")
    fun update(@PathVariable id: Long, @RequestBody request: TestWriteRequest): TestResponse =
        response(service.update(requireId(id), request.requireValue()))

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    fun delete(@PathVariable id: Long) {
        service.delete(requireId(id))
    }

    private fun requireId(id: Long): Long {
        if (id <= 0) throw InvalidTestRequestException()
        return id
    }

    private fun response(record: TestRecord): TestResponse = TestResponse(record.id!!, record.value)
}
