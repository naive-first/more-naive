package com.naivefirst.morenaive

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.ResultActionsDsl
import org.springframework.test.web.servlet.get

@SpringBootTest
@AutoConfigureMockMvc
class ApiDocsTest @Autowired constructor(
    private val mvc: MockMvc,
    private val mapper: ObjectMapper,
) {
    @Test
    @DisplayName("API 명세는 test API 5개만 담고 각 API의 설명과 발생 가능한 응답 코드를 정확히 명시한다")
    fun `API 명세는 test API 5개만 담고 각 API의 설명과 발생 가능한 응답 코드를 정확히 명시한다`() {
        // Given: 각 API가 실제로 반환하는 상태 코드
        val expectedResponseCodes = mapOf(
            "/api/tests" to mapOf("post" to setOf("201", "400"), "get" to setOf("200")),
            "/api/tests/{id}" to mapOf(
                "get" to setOf("200", "400", "404"),
                "put" to setOf("200", "400", "404"),
                "delete" to setOf("204", "400", "404"),
            ),
        )
        // When
        val paths = fetchApiDocs()["paths"]
        // Then: actuator 같은 다른 경로는 명세에 없다.
        assertThat(paths.fieldNames().asSequence().toSet()).isEqualTo(expectedResponseCodes.keys)
        for ((path, operations) in expectedResponseCodes) {
            assertThat(paths[path].fieldNames().asSequence().toSet()).isEqualTo(operations.keys)
            for ((method, responseCodes) in operations) {
                val operation = paths[path][method]
                assertThat(operation["tags"].map { it.asText() }).containsExactly("테스트 행")
                assertThat(operation["summary"]?.asText()).isNotBlank()
                assertThat(operation["description"]?.asText()).isNotBlank()
                val responses = operation["responses"]
                assertThat(responses.fieldNames().asSequence().toSet()).isEqualTo(responseCodes)
                for (errorCode in responseCodes.intersect(setOf("400", "404"))) {
                    assertThat(responses[errorCode]["description"].asText()).isNotBlank()
                    val errorSchemaRef = responses[errorCode]["content"].first()["schema"]["\$ref"].asText()
                    assertThat(errorSchemaRef).isEqualTo("#/components/schemas/TestApiErrorResponse")
                }
            }
        }
    }

    @Test
    @DisplayName("API 명세의 요청·응답 스키마와 ID 경로 변수는 실제 입력 제약을 드러낸다")
    fun `API 명세의 요청·응답 스키마와 ID 경로 변수는 실제 입력 제약을 드러낸다`() {
        // Given / When
        val apiDocs = fetchApiDocs()
        val schemas = apiDocs["components"]["schemas"]
        // Then: value는 JSON 문자열만 허용한다.
        val writeRequest = schemas["TestWriteRequest"]
        assertThat(writeRequest["required"].map { it.asText() }).containsExactly("value")
        assertThat(writeRequest["properties"]["value"]["type"].asText()).isEqualTo("string")
        val response = schemas["TestResponse"]
        assertThat(response["required"].map { it.asText() }).containsExactlyInAnyOrder("id", "value")
        assertThat(response["properties"]["id"]["format"].asText()).isEqualTo("int64")
        assertThat(response["properties"]["value"]["type"].asText()).isEqualTo("string")
        assertThat(schemas["TestApiErrorResponse"]["required"].map { it.asText() }).containsExactly("message")
        for (method in listOf("get", "put", "delete")) {
            val idParameter = apiDocs["paths"]["/api/tests/{id}"][method]["parameters"].single { it["name"].asText() == "id" }
            assertThat(idParameter["required"].asBoolean()).isTrue()
            assertThat(idParameter["schema"]["minimum"].asLong()).isEqualTo(1L)
        }
    }

    @Test
    @DisplayName("게이트웨이가 붙인 /backend prefix와 https를 Swagger 설정과 서버 주소에 반영한다")
    fun `게이트웨이가 붙인 backend prefix와 https를 Swagger 설정과 서버 주소에 반영한다`() {
        // Given: Istio 라우트가 설정하는 전달 헤더
        val gatewayHeaders: MockHttpServletRequestDsl.() -> Unit = {
            header("X-Forwarded-Prefix", "/backend")
            header("X-Forwarded-Proto", "https")
        }
        // When
        val swaggerConfig = readJson(mvc.get("/v3/api-docs/swagger-config", dsl = gatewayHeaders))
        val serverUrl = readJson(mvc.get("/v3/api-docs", dsl = gatewayHeaders))["servers"][0]["url"].asText()
        // Then: 브라우저가 /backend 아래에서 명세를 받고 Try it out도 /backend로 호출한다.
        assertThat(swaggerConfig["configUrl"].asText()).isEqualTo("/backend/v3/api-docs/swagger-config")
        assertThat(swaggerConfig["url"].asText()).isEqualTo("/backend/v3/api-docs")
        assertThat(serverUrl).startsWith("https://").endsWith("/backend")
    }

    @Test
    @DisplayName("Swagger UI 화면을 제공한다")
    fun `Swagger UI 화면을 제공한다`() {
        // Given / When / Then
        mvc.get("/swagger-ui/index.html").andExpect {
            status { isOk() }
            content { contentTypeCompatibleWith(MediaType.TEXT_HTML) }
        }
    }

    private fun fetchApiDocs(): JsonNode = readJson(mvc.get("/v3/api-docs"))

    private fun readJson(result: ResultActionsDsl): JsonNode {
        val body = result.andExpect { status { isOk() } }.andReturn().response.contentAsString
        return mapper.readTree(body)
    }
}
