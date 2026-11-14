package com.naivefirst.morenaive

import org.springframework.stereotype.Service
import org.springframework.data.domain.Sort
import org.springframework.transaction.annotation.Transactional

@Service
class TestRecordService(private val records: TestRecordRepository) {
    @Transactional
    fun create(value: String): TestRecord = records.save(TestRecord(value))

    @Transactional(readOnly = true)
    fun list(): List<TestRecord> = records.findAll(Sort.by("id"))

    @Transactional(readOnly = true)
    fun get(id: Long): TestRecord = records.findById(id).orElseThrow { TestRecordNotFoundException() }
}

class TestRecordNotFoundException : RuntimeException()
