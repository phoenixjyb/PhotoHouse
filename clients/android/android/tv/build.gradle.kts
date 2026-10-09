import java.util.Properties

plugins { id("com.android.application"); kotlin("android") }
val localConfig = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val configuredOrigin = providers.gradleProperty("photohouseTvOrigin").orElse(localConfig.getProperty("photohouseTvOrigin", "")).get()
val configuredLanAddress = providers.gradleProperty("photohouseTvLanAddress").orElse(localConfig.getProperty("photohouseTvLanAddress", "")).get()
val configuredUpdateOrigin = providers.gradleProperty("photohouseTvUpdateOrigin").orElse(localConfig.getProperty("photohouseTvUpdateOrigin", "")).get()
val configuredUpdateLanAddress = providers.gradleProperty("photohouseTvUpdateLanAddress").orElse(localConfig.getProperty("photohouseTvUpdateLanAddress", "")).get()
val configuredCatalogVersion = providers.gradleProperty("photohouseTvCatalogVersion").orElse(localConfig.getProperty("photohouseTvCatalogVersion", "1")).get()
require(configuredCatalogVersion in listOf("1", "2", "3")) { "Unsupported TV catalog version" }
val configuredDiscovery = providers.gradleProperty("photohouseTvDiscoveryEnabled").orElse(localConfig.getProperty("photohouseTvDiscoveryEnabled", "false")).get()
require(configuredDiscovery in listOf("true", "false")) { "Invalid discovery switch" }
require(configuredDiscovery != "true" || configuredCatalogVersion in listOf("2", "3")) { "Discovery requires catalog v2 or v3" }
val configuredBrowse = providers.gradleProperty("photohouseTvBrowseEnabled").orElse(localConfig.getProperty("photohouseTvBrowseEnabled", "false")).get()
require(configuredBrowse in listOf("true", "false"))
require(configuredBrowse != "true" || configuredCatalogVersion == "3") { "Readiness browsing requires catalog v3" }
// Private endpoint routing only; no credentials or certificate trust overrides.
require(configuredLanAddress.isEmpty() || configuredOrigin.isNotEmpty()) { "LAN address requires an HTTPS origin" }
require(configuredLanAddress.isEmpty() || configuredLanAddress.matches(Regex("[0-9.]{7,15}"))) { "Invalid LAN address" }
require(configuredOrigin.none { it == '\n' || it == '\r' || it == '"' || it == '\\' }) { "Invalid configured origin" }
require(configuredUpdateLanAddress.isEmpty() || configuredUpdateOrigin.isNotEmpty()) { "OTA LAN address requires an OTA HTTPS origin" }
require(configuredUpdateLanAddress.isEmpty() || configuredUpdateLanAddress.matches(Regex("[0-9.]{7,15}"))) { "Invalid OTA LAN address" }
require(configuredUpdateOrigin.none { it == '\n' || it == '\r' || it == '"' || it == '\\' }) { "Invalid OTA origin" }
val tagLookupEnabled = providers.gradleProperty("photohouseHomeTagLookupEnabled").orElse("false").get()
require(tagLookupEnabled in listOf("true", "false"))
val calendarEnabled = providers.gradleProperty("photohouseHomeCalendarEnabled").orElse("false").get()
require(calendarEnabled in listOf("true", "false"))
require(calendarEnabled != "true" || tagLookupEnabled == "true")
val storyFixtureFlag = providers.gradleProperty("photohouseStoryFixtureEnabled").orElse("false").get()
require(storyFixtureFlag in listOf("true", "false"))
val storyFixtureEnabled = storyFixtureFlag == "true"
android {
    if (storyFixtureEnabled) {
        sourceSets.getByName("debug").java.srcDir("../story-fixture-ui/src/main/java")
        sourceSets.getByName("debug").manifest.srcFile("../story-fixture-ui/src/main/AndroidManifest.xml")
        sourceSets.getByName("androidTest").java.srcDir("../story-fixture-ui/src/androidTest/java")
    }
    sourceSets.getByName("main").res.srcDir("../branding/res")
    namespace = "dev.photohouse.tv"
    compileSdk = 34
    buildToolsVersion = "34.0.0"
    defaultConfig {
        buildConfigField("boolean", "PHOTOHOUSE_HOME_CALENDAR_ENABLED", calendarEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_HOME_TAG_LOOKUP_ENABLED", tagLookupEnabled)
        applicationId = "dev.photohouse.tv"
        minSdk = 26
        targetSdk = 34
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        versionCode = 29
        versionName = "0.29-paced-viewing"
        buildConfigField("int", "PHOTOHOUSE_CATALOG_VERSION", configuredCatalogVersion)
        buildConfigField("boolean", "PHOTOHOUSE_BROWSE_ENABLED", configuredBrowse)
        buildConfigField("boolean", "PHOTOHOUSE_DISCOVERY_ENABLED", configuredDiscovery)
        buildConfigField("String", "PHOTOHOUSE_ORIGIN", "\"$configuredOrigin\"")
        buildConfigField("String", "PHOTOHOUSE_LAN_ADDRESS", "\"$configuredLanAddress\"")
        buildConfigField("String", "PHOTOHOUSE_UPDATE_ORIGIN", "\"$configuredUpdateOrigin\"")
        buildConfigField("String", "PHOTOHOUSE_UPDATE_LAN_ADDRESS", "\"$configuredUpdateLanAddress\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    lint { abortOnError = true; checkReleaseBuilds = false }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}
dependencies {
    implementation("androidx.media3:media3-exoplayer:1.3.1")
    if (storyFixtureEnabled) debugImplementation(project(":story-fixture-core"))
    testImplementation("junit:junit:4.13.2")
    implementation(project(":home-core"))
    implementation(project(":ota-android"))
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.06.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
