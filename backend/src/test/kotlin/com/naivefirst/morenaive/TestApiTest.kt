package com.naivefirst.morenaive

import com.fasterxml.jackson.databind.ObjectMapper
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import org.springframework.transaction.annotation.Transactional

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class TestApiTest @Autowired constructor(
    private val mvc: MockMvc,
    private val mapper: ObjectMapper,
    private val records: TestRecordRepository,
) {
    @Test
    @DisplayName("생성 요청은 자동 ID와 원래 문자열을 반환하고 PostgreSQL에 한 행을 저장한다")
    fun `생성 요청은 자동 ID와 원래 문자열을 반환하고 PostgreSQL에 한 행을 저장한다`() {
        // Given
        val before = records.count()
        // When
        val body = mvc.post("/api/tests") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":" hello 한글 "}"""
        }.andExpect { status { isCreated() } }.andReturn().response.contentAsString
        // Then
        val response = mapper.readTree(body)
        assertThat(response.size()).isEqualTo(2)
        assertThat(response["id"].asLong()).isPositive()
        assertThat(response["value"].asText()).isEqualTo(" hello 한글 ")
        assertThat(records.findById(response["id"].asLong()).orElseThrow().value).isEqualTo(" hello 한글 ")
        assertThat(records.count()).isEqualTo(before + 1)
    }

    @Test
    @DisplayName("같은 value의 생성 요청은 서로 다른 두 행으로 저장한다")
    fun `같은 value의 생성 요청은 서로 다른 두 행으로 저장한다`() {
        // Given
        val before = records.count()
        // When
        val ids = (1..2).map {
            val body = mvc.post("/api/tests") {
                contentType = MediaType.APPLICATION_JSON
                content = """{"value":"duplicate"}"""
            }.andExpect { status { isCreated() } }.andReturn().response.contentAsString
            mapper.readTree(body)["id"].asLong()
        }
        // Then
        assertThat(ids.toSet()).hasSize(2)
        assertThat(records.count()).isEqualTo(before + 2)
    }

    @ParameterizedTest
    @ValueSource(strings = ["{}", "{\"value\":null}", "{\"value\":\"\"}", "{\"value\":\"  \"}", "{\"value\":42}", "{\"value\":true}", "{\"value\":[]}", "{\"value\":{}}", "{", "null", "[]"])
    @DisplayName("잘못된 생성 입력은 message만 포함한400이며 행을 저장하지 않는다")
    fun `잘못된 생성 입력은 message만 포함한400이며 행을 저장하지 않는다`(input: String) {
        // Given
        val before = records.count()
        // When
        val body = mvc.post("/api/tests") {
            contentType = MediaType.APPLICATION_JSON
            content = input
        }.andExpect { status { isBadRequest() } }.andReturn().response.contentAsString
        // Then
        val response = mapper.readTree(body)
        assertThat(response.size()).isEqualTo(1)
        assertThat(response["message"].asText()).isNotBlank()
        assertThat(records.count()).isEqualTo(before)
    }
}
