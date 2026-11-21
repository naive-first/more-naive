package com.naivefirst.morenaive

import org.springframework.data.jpa.repository.JpaRepository

interface TestRecordRepository : JpaRepository<TestRecord, Long>
