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
