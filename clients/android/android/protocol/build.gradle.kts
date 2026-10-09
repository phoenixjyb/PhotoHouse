plugins { `java-library`; kotlin("jvm"); kotlin("plugin.serialization") }
kotlin { jvmToolchain(17) }
dependencies { api("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3") }
