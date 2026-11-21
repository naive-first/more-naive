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
import org.springframework.test.web.servlet.delete
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
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

    @Test
    @DisplayName("생성한 행의value만 수정하고 재조회하며 다른행은 보존한다")
    fun `생성한 행의value만 수정하고 재조회하며 다른행은 보존한다`() {
        // Given
        val body = mvc.post("/api/tests") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"before"}"""
        }.andExpect { status { isCreated() } }.andReturn().response.contentAsString
        val id = mapper.readTree(body)["id"].asLong()
        val other = records.saveAndFlush(TestRecord("untouched"))
        // When
        mvc.put("/api/tests/$id") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"after"}"""
        }.andExpect {
            status { isOk() }
            jsonPath("$.id") { value(id) }
            jsonPath("$.value") { value("after") }
        }
        // Then
        mvc.get("/api/tests/$id").andExpect { jsonPath("$.value") { value("after") } }
        assertThat(records.findById(other.id!!).orElseThrow().value).isEqualTo("untouched")
        assertThat(records.count()).isEqualTo(2)
    }

    @Test
    @DisplayName("없는 ID수정은404이며 새 행을 생성하지 않는다")
    fun `없는 ID수정은404이며 새 행을 생성하지 않는다`() {
        // Given
        val before = records.count()
        // When / Then
        mvc.put("/api/tests/9223372036854775807") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"after"}"""
        }.andExpect {
            status { isNotFound() }
            jsonPath("$.message") { exists() }
        }
        assertThat(records.count()).isEqualTo(before)
    }

    @ParameterizedTest
    @ValueSource(strings = ["{}", "{\"value\":\"\"}", "{"])
    @DisplayName("잘못된 수정입력은400이며 기존value가 남는다")
    fun `잘못된 수정입력은400이며 기존value가 남는다`(input: String) {
        // Given
        val record = records.saveAndFlush(TestRecord("before"))
        // When / Then
        mvc.put("/api/tests/${record.id}") {
            contentType = MediaType.APPLICATION_JSON
            content = input
        }.andExpect {
            status { isBadRequest() }
            jsonPath("$.message") { exists() }
        }
        assertThat(records.findById(record.id!!).orElseThrow().value).isEqualTo("before")
        assertThat(records.count()).isEqualTo(1)
    }

    @Test
    @DisplayName("잘못된 ID수정은400이며 행을 만들지 않는다")
    fun `잘못된 ID수정은400이며 행을 만들지 않는다`() {
        // Given / When / Then
        mvc.put("/api/tests/0") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"after"}"""
        }.andExpect { status { isBadRequest() } }
        assertThat(records.count()).isZero()
    }

    @Test
    @DisplayName("CRUD후 지정행 삭제는204이고 재조회와 재삭제는404이며 다른행이 남는다")
    fun `CRUD후 지정행 삭제는204이고 재조회와 재삭제는404이며 다른행이 남는다`() {
        // Given
        val created = mvc.post("/api/tests") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"before"}"""
        }.andExpect { status { isCreated() } }.andReturn().response.contentAsString
        val id = mapper.readTree(created)["id"].asLong()
        val other = records.saveAndFlush(TestRecord("untouched"))
        mvc.get("/api/tests/$id").andExpect { jsonPath("$.value") { value("before") } }
        mvc.put("/api/tests/$id") {
            contentType = MediaType.APPLICATION_JSON
            content = """{"value":"after"}"""
        }.andExpect { status { isOk() } }
        // When
        mvc.delete("/api/tests/$id").andExpect {
            status { isNoContent() }
            content { string("") }
        }
        // Then
        mvc.get("/api/tests/$id").andExpect { status { isNotFound() } }
        mvc.delete("/api/tests/$id").andExpect {
            status { isNotFound() }
            jsonPath("$.message") { exists() }
        }
        mvc.get("/api/tests/${other.id}").andExpect {
            status { isOk() }
            jsonPath("$.value") { value("untouched") }
        }
        assertThat(records.count()).isEqualTo(1)
        assertThat(records.findById(id)).isEmpty()
    }

    @Test
    @DisplayName("처음부터 없는 행의삭제는404이고 다른행을 지우지 않는다")
    fun `처음부터 없는 행의삭제는404이고 다른행을 지우지 않는다`() {
        // Given
        val other = records.saveAndFlush(TestRecord("untouched"))
        // When / Then
        mvc.delete("/api/tests/9223372036854775807").andExpect { status { isNotFound() } }
        assertThat(records.findById(other.id!!)).isPresent()
        assertThat(records.count()).isEqualTo(1)
    }

    @ParameterizedTest
    @ValueSource(strings = ["abc", "0", "9223372036854775808"])
    @DisplayName("잘못된 ID삭제는400이고 데이터를 지우지 않는다")
    fun `잘못된 ID삭제는400이고 데이터를 지우지 않는다`(id: String) {
        // Given
        val other = records.saveAndFlush(TestRecord("untouched"))
        // When / Then
        mvc.delete("/api/tests/$id").andExpect { status { isBadRequest() } }
        assertThat(records.findById(other.id!!)).isPresent()
        assertThat(records.count()).isEqualTo(1)
    }
}
