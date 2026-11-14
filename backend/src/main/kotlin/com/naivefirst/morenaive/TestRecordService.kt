package com.naivefirst.morenaive

import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class TestRecordService(private val records: TestRecordRepository) {
    @Transactional
    fun create(value: String): TestRecord = records.save(TestRecord(value))
}
