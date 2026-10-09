plugins { `java-library`; kotlin("jvm") }
kotlin { jvmToolchain(17) }
dependencies {
    api(project(":playback-core"))
    api("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("com.squareup.okhttp3:okhttp-tls:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("junit:junit:4.13.2")
}

// Ordinary tests remain synthetic and loopback-only. Real LAN reads need explicit opt-in.
tasks.test { exclude("**/HomeLanPilotTest*", "**/CatalogLanPilotTest*") }
tasks.register<Test>("lanPilotTest") {
    description = "Read the explicitly authorized synthetic LAN feed using in-app address mapping"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    include("**/HomeLanPilotTest.class")
    outputs.upToDateWhen { false }
    doFirst {
        require(System.getenv("PHOTOHOUSE_HOME_TEST_ORIGIN") != null && System.getenv("PHOTOHOUSE_HOME_TEST_ADDRESS") != null) {
            "Explicit private synthetic home-feed origin and address are required"
        }
    }
}

tasks.register<Test>("catalogLanPilotTest") {
    description = "Read an explicitly approved real catalog canary through the production adapter"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    include("**/CatalogLanPilotTest.class")
    outputs.upToDateWhen { false }
    doFirst {
        require(System.getenv("PHOTOHOUSE_CATALOG_LIVE_APPROVED") == "true") {
            "Explicit live catalog approval and private canary inputs are required"
        }
    }
}
