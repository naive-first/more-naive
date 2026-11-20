package com.naivefirst.morenaive

import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get

@SpringBootTest
@AutoConfigureMockMvc
class ApplicationTest(@Autowired private val mvc: MockMvc) {
    @Test
    @DisplayName("앱 생존과 준비 상태를 조회할 수 있다")
    fun `앱 생존과 준비 상태를 조회할 수 있다`() {
        // Given: 기본 앱 설정
        // When / Then: 두 probe가 정상이고 내부 상세는 노출하지 않는다.
        for (probe in listOf("liveness", "readiness")) {
            mvc.get("/actuator/health/$probe").andExpect {
                status { isOk() }
                jsonPath("$.status") { value("UP") }
                jsonPath("$.components") { doesNotExist() }
            }
        }
    }

    @Test
    @DisplayName("환경변수 actuator는 공개하지 않는다")
    fun `환경변수 actuator는 공개하지 않는다`() {
        // Given: health만 허용한 설정
        // When / Then
        mvc.get("/actuator/env").andExpect { status { isNotFound() } }
    }
}
