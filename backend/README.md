# Backend

JDK 21·Gradle 8.14.3·Kotlin 2.2.21·Spring Boot 3.5.16으로 실행하는 최소 backend입니다. PostgreSQL 17.12에 연결하며 test CRUD는 후속 #30–#33에서 추가합니다. [Spring Boot 지원 도구](https://docs.spring.io/spring-boot/3.5/system-requirements.html)와 [Kotlin Gradle 호환 범위](https://kotlinlang.org/docs/gradle-configure-project.html)를 기준으로 고정했습니다.

## 앱 실행과 이미지

저장소 루트에서 루트 `.env.example`을 참고해 실제 `.env`를 준비하고 권한을 600으로 제한합니다. 필요한 키는 `LOCAL_DB_DATABASE`·`LOCAL_DB_USERNAME`·`LOCAL_DB_PASSWORD`·`LOCAL_DB_PORT`·`LOCAL_DB_URL`입니다. URL은 Compose의 호스트 포트와 일치하는 `jdbc:postgresql://127.0.0.1:포트/DB이름`입니다. 포트는 8080이며 종료 신호를 받으면 최대 20초 동안 진행 중인 요청을 마무리합니다.

```sh
python3 scripts/env.py local-compose -- docker compose --env-file .env -f backend/compose.yaml up -d --wait
python3 scripts/env.py local-app -- backend/gradlew -p backend test bootJar
python3 scripts/env.py local-app -- java -jar backend/build/libs/app.jar
curl --fail http://localhost:8080/actuator/health/liveness
curl --fail http://localhost:8080/actuator/health/readiness
```

두 probe의 `status`는 정상 시 `UP`입니다. [Actuator probe](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)는 health만 노출하며 환경변수·내부 상세는 반환하지 않습니다. readiness는 DB 접속을 포함하고 DB 중단 시 503입니다. liveness는 프로세스 상태만 확인하므로 일시 DB 장애를 재시작 신호로 사용하지 않습니다.

```sh
docker build -t more-naive-backend:local backend
python3 scripts/env.py local-app -- docker run --rm --network host --name more-naive-backend-local -e DB_URL -e DB_USERNAME -e DB_PASSWORD more-naive-backend:local
docker stop --time 25 more-naive-backend-local
```

이미지는 고정 digest의 Temurin JRE 21 위에 같은 `app.jar`만 복사하고 UID/GID 10001로 실행합니다. 위 `--network host` 예시는 Linux 로컬 Docker용이며 loopback DB에 접속합니다. 다른 OS/배포에서는 컨테이너에서 도달하는 DB URL을 명시합니다. build context allowlist는 JAR만 허용하므로 루트 `.env`·state·kubeconfig·소스가 이미지에 들어가지 않습니다. `Unable to access jarfile`이면 먼저 `bootJar`를 실행합니다. 포트 충돌이면 기존 서비스를 정지시키지 말고 실행 포트를 바꿉니다. 컨테이너 재생성은 앱 프로세스만 교체합니다.

local 실행은 #41의 `python3 scripts/env.py local-app -- backend/gradlew -p backend bootRun`도 사용할 수 있습니다. Spring이 루트 `.env`를 자동으로 읽는다고 가정하지 않으며, CI는 격리된 PostgreSQL의 `DB_URL`·`DB_USERNAME`·`DB_PASSWORD`를 직접 주입하고 `backend/gradlew -p backend test bootJar`를 실행합니다. prod는 Secret/ConfigMap에서 같은 세 키를 주입하며 누락 시 local 값으로 대체하지 않습니다. dev 클러스터 배포는 만들지 않습니다.

## PostgreSQL와 migration

앱 시작 시 Boot 3.5.16 BOM이 고정한 Flyway가 `db/migration/V1__create_test.sql`을 적용하고 Hibernate는 `ddl-auto=validate`로 확인만 합니다. [단일 migration 도구 사용 지침](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html#howto.data-initialization.migration-tool)을 따르며 자동 schema update와 시작 시 초기 데이터 삽입은 하지 않습니다. `test.id`는 자동 생성 bigint, `test.value`는 NOT NULL text입니다. migration 재실행은 이력을 읽어 적용 완료한 V1을 반복하지 않습니다.

잘못된 인증·schema 불일치·migration 실패는 시작 실패로 확인합니다. 원인을 고친 뒤 다시 실행하며 적용한 SQL 파일을 수정하거나 `clean`으로 지우지 않습니다. 로컬 중지는 `docker compose --env-file .env -f backend/compose.yaml down`이며 named volume 데이터는 남습니다. `down -v`는 로컬 DB 전체를 삭제하므로 일반 정리 명령으로 사용하지 않습니다. 테스트는 격리된 DB에서 트랜잭션 rollback 또는 직접 만든 행만 정리합니다. 백업·복원은 이번 범위에 추가하지 않습니다.

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
