import java.util.Properties

plugins { id("com.android.application"); kotlin("android") }
val localConfig = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val configuredOrigin = providers.gradleProperty("photohouseOrigin").orElse(localConfig.getProperty("photohouseOrigin", "")).get()
// Only an origin is configurable; no credentials or trust overrides are build inputs.
require(configuredOrigin.none { it == '\n' || it == '\r' || it == '"' || it == '\\' }) { "Invalid configured origin" }
val protectedNativeV2Enabled = providers.gradleProperty("photohouseProtectedNativeV2Enabled").orElse("false").get()
require(protectedNativeV2Enabled in listOf("true", "false"))
val uploadEnabled = providers.gradleProperty("photohousePhoneUploadEnabled").orElse("false").get()
require(uploadEnabled in listOf("true", "false"))
require(uploadEnabled != "true" || protectedNativeV2Enabled == "true")
val discoveryEnabled = providers.gradleProperty("photohousePhoneDiscoveryEnabled").orElse("false").get()
require(discoveryEnabled in listOf("true", "false")) { "Invalid phone discovery switch" }
val familyTagsEnabled = providers.gradleProperty("photohousePhoneFamilyTagsEnabled").orElse("false").get()
require(familyTagsEnabled in listOf("true", "false")) { "Invalid family tags switch" }
require(familyTagsEnabled != "true" || protectedNativeV2Enabled == "true")
val photoDeliveryEnabled = providers.gradleProperty("photohousePhonePhotoDeliveryEnabled").orElse("false").get()
require(photoDeliveryEnabled in listOf("true", "false"))
val preparedVideoEnabled = providers.gradleProperty("photohousePhonePreparedVideoEnabled").orElse("false").get()
require(preparedVideoEnabled in listOf("true", "false"))
require(preparedVideoEnabled != "true" || protectedNativeV2Enabled == "true")
val mediaFilterEnabled = providers.gradleProperty("photohousePhoneMediaFilterEnabled").orElse("false").get()
require(mediaFilterEnabled in listOf("true", "false"))
require(mediaFilterEnabled != "true" || protectedNativeV2Enabled == "true")
val preparedBrowseEnabled = providers.gradleProperty("photohousePhonePreparedBrowseEnabled").orElse("false").get()
require(preparedBrowseEnabled in listOf("true", "false"))
require(preparedBrowseEnabled != "true" || mediaFilterEnabled == "true" && preparedVideoEnabled == "true")
// Home mode has independent routing. Neither field can carry account credentials.
val homeOrigin = providers.gradleProperty("photohousePhoneHomeOrigin").orElse(localConfig.getProperty("photohousePhoneHomeOrigin", "")).get()
val homeAddress = providers.gradleProperty("photohousePhoneHomeLanAddress").orElse(localConfig.getProperty("photohousePhoneHomeLanAddress", "")).get()
for (value in listOf(homeOrigin, homeAddress)) require(value.none { it == '\n' || it == '\r' || it == '"' || it == '\\' })
val homeDiscoveryEnabled = providers.gradleProperty("photohousePhoneHomeDiscoveryEnabled").orElse("false").get()
require(homeDiscoveryEnabled in listOf("true", "false"))
val tagLookupEnabled = providers.gradleProperty("photohouseHomeTagLookupEnabled").orElse("false").get()
require(tagLookupEnabled in listOf("true", "false"))
val assistantEnabled = providers.gradleProperty("photohouseAssistantEnabled").orElse("false").get()
require(assistantEnabled in listOf("true", "false"))
val memoryCommunityEnabled = providers.gradleProperty("photohouseMemoryCommunityEnabled").orElse("false").get()
require(memoryCommunityEnabled in listOf("true", "false"))
require(memoryCommunityEnabled != "true" || protectedNativeV2Enabled == "true")
val calendarEnabled = providers.gradleProperty("photohouseHomeCalendarEnabled").orElse("false").get()
require(calendarEnabled in listOf("true", "false"))
require(calendarEnabled != "true" || tagLookupEnabled == "true")
val storyFixtureFlag = providers.gradleProperty("photohouseStoryFixtureEnabled").orElse("false").get()
require(storyFixtureFlag in listOf("true", "false"))
val storyFixtureEnabled = storyFixtureFlag == "true"
// A separate, unconfigured package for synthetic checks on a physical phone.
// It cannot replace the family app or construct a configured network client.
val uiQa = providers.gradleProperty("photohousePhoneUiQa").orElse("false").get()
require(uiQa in listOf("true", "false"))
require(uiQa != "true" || (configuredOrigin.isEmpty() && homeOrigin.isEmpty() && homeAddress.isEmpty()))
android {
    if (storyFixtureEnabled) {
        sourceSets.getByName("debug").java.srcDir("../story-fixture-ui/src/main/java")
        sourceSets.getByName("debug").manifest.srcFile("../story-fixture-ui/src/main/AndroidManifest.xml")
        sourceSets.getByName("androidTest").java.srcDir("../story-fixture-ui/src/androidTest/java")
    }
    sourceSets.getByName("main").res.srcDir("../branding/res")
    namespace = "dev.photohouse.connected"
    compileSdk = 34
    buildToolsVersion = "34.0.0"
    defaultConfig {
        buildConfigField("boolean", "PHOTOHOUSE_HOME_CALENDAR_ENABLED", calendarEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_HOME_TAG_LOOKUP_ENABLED", tagLookupEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_ASSISTANT_ENABLED", assistantEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_MEMORY_COMMUNITY_ENABLED", memoryCommunityEnabled)
        applicationId = if (uiQa == "true") "dev.photohouse.connected.qa" else "dev.photohouse.connected"
        minSdk = 26
        targetSdk = 34
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        versionCode = 46
        versionName = "0.46-conversation-continuity"
        buildConfigField("boolean", "PHOTOHOUSE_HOME_DISCOVERY_ENABLED", homeDiscoveryEnabled)
        buildConfigField("String", "PHOTOHOUSE_HOME_ORIGIN", "\"$homeOrigin\"")
        buildConfigField("String", "PHOTOHOUSE_HOME_LAN_ADDRESS", "\"$homeAddress\"")
        buildConfigField("boolean", "PHOTOHOUSE_PROTECTED_NATIVE_V2_ENABLED", protectedNativeV2Enabled)
        buildConfigField("boolean", "PHOTOHOUSE_UPLOAD_ENABLED", uploadEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_DISCOVERY_ENABLED", discoveryEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_FAMILY_TAGS_ENABLED", familyTagsEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_PHOTO_DELIVERY_ENABLED", photoDeliveryEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_PREPARED_VIDEO_ENABLED", preparedVideoEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_MEDIA_FILTER_ENABLED", mediaFilterEnabled)
        buildConfigField("boolean", "PHOTOHOUSE_PREPARED_BROWSE_ENABLED", preparedBrowseEnabled)
        buildConfigField("String", "PHOTOHOUSE_ORIGIN", "\"$configuredOrigin\"")
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
    implementation(project(":live-core"))
    implementation(project(":home-core"))
    implementation(project(":ota-android"))
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.06.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    // The Compose test runner calls Trace.forceEnableAppTracing(), added after 1.0.0.
    // Keep the compatible implementation scoped to debug/test runtime only.
    debugImplementation("androidx.tracing:tracing:1.2.0")
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    testImplementation("junit:junit:4.13.2")
}
