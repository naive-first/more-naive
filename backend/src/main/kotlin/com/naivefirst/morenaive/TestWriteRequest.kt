package com.naivefirst.morenaive

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.NullNode
import io.swagger.v3.oas.annotations.media.Schema

@Schema(description = "테스트 행 생성·수정 요청")
data class TestWriteRequest(
    @field:Schema(
        description = "저장할 문자열. 비어 있거나 공백만 있으면 400이며, 앞뒤 공백은 그대로 저장합니다.",
        implementation = String::class,
        example = "hello",
        pattern = ".*\\S.*",
        requiredMode = Schema.RequiredMode.REQUIRED,
    )
    val value: JsonNode = NullNode.instance,
) {
    fun requireValue(): String {
        val text = value.takeIf { it.isTextual }?.textValue()
        if (text.isNullOrBlank()) throw InvalidTestRequestException()
        return text
    }
}

class InvalidTestRequestException : RuntimeException()
