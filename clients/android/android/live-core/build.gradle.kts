plugins { `java-library`; kotlin("jvm") }
kotlin { jvmToolchain(17) }
dependencies {
    api(project(":playback-core"))
    api(project(":protocol"))
    api("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("com.squareup.okhttp3:okhttp-tls:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("junit:junit:4.13.2")
}
sourceSets.test { resources.srcDir("../../contracts/v1") }
tasks.processTestResources { from("../phone-discovery-contract") { include("examples.json") } }
tasks.processTestResources { from("../protected-native-contract") { into("protected-native-contract") } }
tasks.processTestResources { from("../story-workspace-contract") { into("story-workspace-contract") } }

// Explicit opt-in: a real pinned backend and existing Python runtime are required.
// The ordinary test task continues to run without a backend checkout.
tasks.test { exclude("**/BackendIntegrationTest*") }
tasks.register<Test>("backendIntegrationTest") {
    description = "Exercise the real HTTPS adapter against a disposable pinned backend"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    include("**/BackendIntegrationTest.class")
    outputs.upToDateWhen { false }
    doFirst {
        require(System.getenv("PHOTOHOUSE_TEST_BACKEND") != null && System.getenv("PHOTOHOUSE_TEST_PYTHON") != null) {
            "Run android/integration/verify-backend.py with an explicit backend checkout and interpreter"
        }
    }
}
