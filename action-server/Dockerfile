# Kairon action server (Java port). Build from this directory:
#   docker build -t kairon-action-server-java .
# Required at runtime: FERNET_KEY, SECRET_KEY, ASYNC_CALLBACK_AES_KEY, ASYNC_CALLBACK_AES_IV (see CONFIG.md).

FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY gradlew settings.gradle build.gradle gradle.properties ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew --no-daemon --console=plain dependencies > /dev/null
COPY src ./src
RUN ./gradlew --no-daemon --console=plain installDist -x test

FROM eclipse-temurin:21-jre
RUN groupadd --system kairon && useradd --system --gid kairon --home-dir /app kairon
WORKDIR /app
COPY --from=build /src/build/install/kairon-action /app
USER kairon
EXPOSE 5055
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75"
ENTRYPOINT ["/app/bin/kairon-action"]
