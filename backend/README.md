# Backend

JDK 21과 공식 Gradle Wrapper 8.14.3을 사용합니다. 현재 단계는 실행 도구만 준비하며 앱 소스·의존성·Dockerfile은 후속 #17에서 추가합니다. `test`와 `bootJar` 성공을 의미하지 않습니다.

## Wrapper 확인

저장소 루트에서 실행합니다. 처음에는 Gradle 배포본 다운로드를 위한 HTTPS 접근이 필요합니다.

```sh
cd backend
./gradlew --version
sha256sum gradle/wrapper/gradle-wrapper.jar
```

Windows에서는 JDK 21 설치 후 `gradlew.bat --version`을 사용합니다. Linux 검증으로 Windows 실행까지 확인한 것은 아닙니다.

공식 `gradle-8.14.3-bin.zip`을 검증한 뒤 빈 임시 프로젝트에서 `gradle wrapper`로 생성했습니다. 배포본과 JAR의 값은 [Gradle 공식 checksum](https://gradle.org/release-checksums/)과 대조합니다. [Wrapper 검증과 배포본 checksum 설정](https://docs.gradle.org/current/userguide/gradle_wrapper.html#sec:verification)을 따릅니다.

| 대상 | 고정값 |
| --- | --- |
| 배포본 | `https://services.gradle.org/distributions/gradle-8.14.3-bin.zip` |
| 배포본 SHA-256 | `bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531` |
| Wrapper JAR 크기 | 43,764 bytes |
| Wrapper JAR SHA-256 | `7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172` |

`distributionSha256Sum`이 맞지 않으면 다운로드한 배포본을 실행하지 않습니다. 실패 시 JDK 버전·HTTPS 연결·공식 checksum을 확인하며 검증을 비활성화하지 않습니다. 재실행은 같은 버전의 사용자 Gradle 캐시를 재사용합니다. Wrapper 삭제는 실행 도구만 제거하고 DB나 클러스터에 영향을 주지 않습니다.

## Test API 계약

아래는 #29–#33에서 구현할 계약과 요청 예시이며 실제 배포 성공 기록이 아닙니다. 배포 확인용 `test` 테이블의 행을 다룹니다. HTTP로 테이블 DDL을 실행하지 않습니다.

테이블은 자동 생성 `bigint id`와 필수 `text value`만 저장합니다. value 중복을 허용하며 인증·회원·검색·페이징·추가 업무 규칙은 넣지 않습니다. 생성한 행은 배포 확인용 데이터이므로 사용한 id를 기록하고 검증 후 해당 행만 삭제합니다.

| 요청 | 성공 응답 | 기본 오류 |
| --- | --- | --- |
| `POST /api/tests`, `{"value":"hello"}` | 201, `{"id":1,"value":"hello"}` | 누락/null/빈 value·잘못된 JSON은 400 |
| `GET /api/tests` | 200, id 오름차순 배열, 빈 DB는 `[]` | |
| `GET /api/tests/{id}` | 200, id/value 객체 | 잘못된 ID는 400, 없는 ID는 404 |
| `PUT /api/tests/{id}`, `{"value":"changed"}` | 200, 같은 id와 변경된 value | 잘못된 ID/JSON/value는 400, 없는 ID는 404 |
| `DELETE /api/tests/{id}` | 204, 응답 body 없음 | 잘못된 ID는 400, 없는 ID·재삭제는 404 |

ID는 양의 bigint 숫자입니다. value는 공백만 있는 문자열을 빈 값으로 처리하되, 정상 문자열의 앞뒤 공백을 임의로 제거하지 않습니다. 오류 응답은 `{"message":"..."}` 한 필드이며 내부 예외·접속 정보는 반환하지 않습니다. 예시의 id와 message 문구는 설명용입니다.

```sh
API_BASE_URL=http://localhost:8080
curl -i -H 'Content-Type: application/json' -d '{"value":"hello"}' "$API_BASE_URL/api/tests"
# 생성 응답의 실제 id를 아래 ID에 넣습니다.
ID=1
curl -i "$API_BASE_URL/api/tests"
curl -i "$API_BASE_URL/api/tests/$ID"
curl -i -X PUT -H 'Content-Type: application/json' -d '{"value":"changed"}' "$API_BASE_URL/api/tests/$ID"
curl -i -X DELETE "$API_BASE_URL/api/tests/$ID"
curl -i "$API_BASE_URL/api/tests/$ID"
curl -i -X DELETE "$API_BASE_URL/api/tests/$ID"
```

삭제 후 조회·재삭제는 404여야 합니다. 다른 사용자가 만든 행을 정리하거나 테이블을 비우지 않습니다. prod에서는 배포 이슈의 명시적 쓰기 검증 절차와 실제 HTTPS 주소를 사용합니다.
