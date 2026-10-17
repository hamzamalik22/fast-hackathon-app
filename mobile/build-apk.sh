#!/usr/bin/env bash
# Builds the installable release APK at mobile/release/app-release.apk (spec 1.3 / 8.1).
# Release build signed with the Expo template's debug keystore, so it installs directly via adb.
# Usage: ./build-apk.sh            (incremental)
#        ./build-apk.sh --clean    (regenerate android/ from app.json first, e.g. after adding a native module)
set -euo pipefail
cd "$(dirname "$0")"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"

[ -d node_modules ] || npm ci --no-audit --no-fund
if [ "${1:-}" = "--clean" ] || [ ! -d android ]; then
  npx expo prebuild -p android --clean --no-install
fi
(cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,x86_64 --console=plain)
mkdir -p release
cp android/app/build/outputs/apk/release/app-release.apk release/app-release.apk
ls -lh release/app-release.apk
