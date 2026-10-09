plugins { `java-library`; kotlin("jvm") }
kotlin { jvmToolchain(17) }
dependencies {
    api("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    testImplementation("junit:junit:4.13.2")
}
