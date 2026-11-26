package com.naivefirst.morenaive

import io.swagger.v3.oas.annotations.media.Schema
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

@Schema(description = "테스트 행")
data class TestResponse(
    @field:Schema(description = "자동 생성 ID", example = "1", requiredMode = Schema.RequiredMode.REQUIRED)
    val id: Long,
    @field:Schema(description = "저장된 문자열. 앞뒤 공백을 포함해 저장한 그대로 반환합니다.", example = "hello", requiredMode = Schema.RequiredMode.REQUIRED)
    val value: String,
)

@RestController
@RequestMapping("/api/tests")
class TestController(private val service: TestRecordService) : TestControllerDocs {
    @PostMapping
    override fun create(@RequestBody request: TestWriteRequest): ResponseEntity<TestResponse> {
        val record = service.create(request.requireValue())
        return ResponseEntity.status(HttpStatus.CREATED).body(response(record))
    }

    @GetMapping
    override fun list(): List<TestResponse> = service.list().map(::response)

    @GetMapping("/{id}")
    override fun get(@PathVariable id: Long): TestResponse = response(service.get(requireId(id)))

    @PutMapping("/{id}")
    override fun update(@PathVariable id: Long, @RequestBody request: TestWriteRequest): TestResponse =
        response(service.update(requireId(id), request.requireValue()))

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    override fun delete(@PathVariable id: Long) {
        service.delete(requireId(id))
    }

    private fun requireId(id: Long): Long {
        if (id <= 0) throw InvalidTestRequestException()
        return id
    }

    private fun response(record: TestRecord): TestResponse = TestResponse(record.id!!, record.value)
}
