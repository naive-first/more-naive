FROM eclipse-temurin:21-jre-jammy@sha256:dff6eb46527bd293a3c06bbbe9e64e8c9f91f01905b5abbdad31761c03059d2c
WORKDIR /app
COPY --chown=10001:10001 build/libs/app.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
