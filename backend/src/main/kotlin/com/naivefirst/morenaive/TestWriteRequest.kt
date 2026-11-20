package com.naivefirst.morenaive

import com.fasterxml.jackson.databind.JsonNode

data class TestWriteRequest(val value: JsonNode? = null) {
    fun requireValue(): String {
        val text = value?.takeIf { it.isTextual }?.textValue()
        if (text.isNullOrBlank()) throw InvalidTestRequestException()
        return text
    }
}

class InvalidTestRequestException : RuntimeException()
