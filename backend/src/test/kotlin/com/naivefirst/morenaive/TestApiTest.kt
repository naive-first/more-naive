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
import org.springframework.test.web.servlet.get
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

    @Test
    @DisplayName("빈 테이블 조회는 빈 배열이며 데이터를 만들지 않는다")
    fun `빈 테이블 조회는 빈 배열이며 데이터를 만들지 않는다`() {
        // Given
        assertThat(records.count()).isZero()
        // When / Then
        mvc.get("/api/tests").andExpect {
            status { isOk() }
            content { json("[]") }
        }
        assertThat(records.count()).isZero()
    }

    @Test
    @DisplayName("목록은 ID오름차순이고 상세는 저장된값이며 조회가 행을 변경하지 않는다")
    fun `목록은 ID오름차순이고 상세는 저장된값이며 조회가 행을 변경하지 않는다`() {
        // Given
        val first = records.saveAndFlush(TestRecord("first"))
        val second = records.saveAndFlush(TestRecord("second"))
        // When
        val body = mvc.get("/api/tests").andExpect { status { isOk() } }.andReturn().response.contentAsString
        mvc.get("/api/tests/${second.id}").andExpect {
            status { isOk() }
            jsonPath("$.id") { value(second.id) }
            jsonPath("$.value") { value("second") }
        }
        // Then
        val rows = mapper.readTree(body)
        assertThat(rows.map { it["id"].asLong() }).containsExactly(first.id, second.id)
        assertThat(rows.map { it["value"].asText() }).containsExactly("first", "second")
        assertThat(rows.all { it.size() == 2 }).isTrue()
        assertThat(records.count()).isEqualTo(2)
        assertThat(records.findById(first.id!!).orElseThrow().value).isEqualTo("first")
    }

    @Test
    @DisplayName("없는 ID조회는 message만 포함한404이며 행을 만들지 않는다")
    fun `없는 ID조회는 message만 포함한404이며 행을 만들지 않는다`() {
        // Given
        val before = records.count()
        // When
        val body = mvc.get("/api/tests/9223372036854775807").andExpect { status { isNotFound() } }.andReturn().response.contentAsString
        // Then
        val error = mapper.readTree(body)
        assertThat(error.size()).isEqualTo(1)
        assertThat(error["message"].asText()).isNotBlank()
        assertThat(records.count()).isEqualTo(before)
    }

    @ParameterizedTest
    @ValueSource(strings = ["abc", "0", "-1", "9223372036854775808"])
    @DisplayName("숫자가 아니거나 양수bigint범위를 벗어난 ID는400이다")
    fun `숫자가 아니거나 양수bigint범위를 벗어난 ID는400이다`(id: String) {
        // Given: 잘못된 ID
        // When
        val body = mvc.get("/api/tests/$id").andExpect { status { isBadRequest() } }.andReturn().response.contentAsString
        // Then
        val error = mapper.readTree(body)
        assertThat(error.size()).isEqualTo(1)
        assertThat(error["message"].asText()).isNotBlank()
    }
}
