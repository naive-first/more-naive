package com.naivefirst.morenaive

import io.swagger.v3.oas.annotations.Operation
import io.swagger.v3.oas.annotations.Parameter
import io.swagger.v3.oas.annotations.media.ArraySchema
import io.swagger.v3.oas.annotations.media.Content
import io.swagger.v3.oas.annotations.media.Schema
import io.swagger.v3.oas.annotations.parameters.RequestBody
import io.swagger.v3.oas.annotations.responses.ApiResponse
import io.swagger.v3.oas.annotations.responses.ApiResponses
import io.swagger.v3.oas.annotations.tags.Tag
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity

@Tag(name = "테스트 행", description = "배포 확인용 test 테이블의 행을 생성·조회·수정·삭제합니다. 인증과 페이징은 없습니다.")
interface TestControllerDocs {
    @Operation(
        summary = "테스트 행 생성",
        description = "value 문자열로 행을 하나 만들고 자동 생성 ID와 함께 반환합니다. 같은 value도 별도 행으로 저장하며 앞뒤 공백을 제거하지 않습니다.",
    )
    @ApiResponses(
        value = [
            ApiResponse(
                responseCode = "201",
                description = "생성 성공",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestResponse::class))],
            ),
            ApiResponse(
                responseCode = "400",
                description = "value가 없거나 null·빈 문자열·공백만 있는 문자열·문자열이 아닌 값이거나, 요청 body가 잘못된 JSON",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
        ],
    )
    fun create(
        @RequestBody(description = "저장할 value", required = true)
        request: TestWriteRequest,
    ): ResponseEntity<TestResponse>

    @Operation(
        summary = "테스트 행 목록 조회",
        description = "모든 행을 ID 오름차순으로 반환합니다. 행이 없으면 빈 배열을 반환합니다.",
    )
    @ApiResponses(
        value = [
            ApiResponse(
                responseCode = "200",
                description = "조회 성공",
                content = [
                    Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        array = ArraySchema(schema = Schema(implementation = TestResponse::class)),
                    ),
                ],
            ),
        ],
    )
    fun list(): List<TestResponse>

    @Operation(summary = "테스트 행 상세 조회", description = "ID로 행 하나를 조회합니다.")
    @ApiResponses(
        value = [
            ApiResponse(
                responseCode = "200",
                description = "조회 성공",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestResponse::class))],
            ),
            ApiResponse(
                responseCode = "400",
                description = "ID가 양의 정수가 아님",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
            ApiResponse(
                responseCode = "404",
                description = "해당 ID의 행이 없음",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
        ],
    )
    fun get(
        @Parameter(description = "조회할 행 ID", required = true, example = "1", schema = Schema(type = "integer", format = "int64", minimum = "1"))
        id: Long,
    ): TestResponse

    @Operation(summary = "테스트 행 수정", description = "ID의 value를 바꾸고 변경된 행을 반환합니다. value 규칙은 생성과 같습니다.")
    @ApiResponses(
        value = [
            ApiResponse(
                responseCode = "200",
                description = "수정 성공",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestResponse::class))],
            ),
            ApiResponse(
                responseCode = "400",
                description = "ID가 양의 정수가 아니거나, value 또는 요청 JSON이 잘못됨",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
            ApiResponse(
                responseCode = "404",
                description = "해당 ID의 행이 없음",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
        ],
    )
    fun update(
        @Parameter(description = "수정할 행 ID", required = true, example = "1", schema = Schema(type = "integer", format = "int64", minimum = "1"))
        id: Long,
        @RequestBody(description = "바꿀 value", required = true)
        request: TestWriteRequest,
    ): TestResponse

    @Operation(summary = "테스트 행 삭제", description = "ID의 행을 삭제합니다. 응답 body는 없으며 이미 삭제한 ID를 다시 요청하면 404입니다.")
    @ApiResponses(
        value = [
            ApiResponse(responseCode = "204", description = "삭제 성공"),
            ApiResponse(
                responseCode = "400",
                description = "ID가 양의 정수가 아님",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
            ApiResponse(
                responseCode = "404",
                description = "해당 ID의 행이 없음",
                content = [Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = Schema(implementation = TestApiErrorResponse::class))],
            ),
        ],
    )
    fun delete(
        @Parameter(description = "삭제할 행 ID", required = true, example = "1", schema = Schema(type = "integer", format = "int64", minimum = "1"))
        id: Long,
    )
}
