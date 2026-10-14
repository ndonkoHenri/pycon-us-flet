// S6: an Android library module that exists only for its manifest, which
// Gradle merges into the app (receivers of flutter_local_notifications and the
// boot permission). Java only, so it needs no Kotlin plugin.
group = "io.github.ndonkohenri.s6reminders"
version = "0.0.1"

buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.13.2")
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

plugins {
    id("com.android.library")
}

android {
    namespace = "io.github.ndonkohenri.s6reminders"
    compileSdk = 36

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        minSdk = 24
    }
}
