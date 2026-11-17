package com.naivefirst.morenaive

import org.assertj.core.api.Assertions.assertThat
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.annotation.Transactional

@SpringBootTest
class PostgresTest @Autowired constructor(
    private val records: TestRecordRepository,
    private val jdbc: JdbcTemplate,
    private val flyway: Flyway,
) {
    @Test
    @Transactional
    @DisplayName("실제 PostgreSQL에 저장하고 자동 생성 ID로 다시 조회한다")
    fun `실제 PostgreSQL에 저장하고 자동 생성 ID로 다시 조회한다`() {
        // Given
        val first = TestRecord("duplicate allowed")
        val second = TestRecord("duplicate allowed")
        // When
        val saved = records.saveAndFlush(first)
        records.saveAndFlush(second)
        // Then
        assertThat(saved.id).isPositive()
        assertThat(records.findById(saved.id!!).orElseThrow().value).isEqualTo("duplicate allowed")
        assertThat(first.id).isNotEqualTo(second.id)
    }

    @Test
    @DisplayName("migration을 재실행해도 동일한 schema를 재생성하지 않는다")
    fun `migration을 재실행해도 동일한 schema를 재생성하지 않는다`() {
        // Given: 앱 시작 때 적용한 V1
        // When
        val result = flyway.migrate()
        // Then
        assertThat(result.migrationsExecuted).isZero()
        assertThat(jdbc.queryForObject("SELECT count(*) FROM flyway_schema_history WHERE success = true", Long::class.java)).isEqualTo(1L)
        val columns = jdbc.queryForList("SELECT column_name FROM information_schema.columns WHERE table_name = 'test' ORDER BY ordinal_position", String::class.java)
        assertThat(columns).containsExactly("id", "value")
    }
}
