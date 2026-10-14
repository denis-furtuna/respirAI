"""Turns the Android project that `npx cap add android` makes into respirAI's. Run in phone/, before `npx cap sync`.

    python android_setup.py          needs Pillow (pip), for the icons

The android/ folder is made fresh on every build (on GitHub) and never committed, so everything that differs from
Capacitor's template is here, in one place:
  - permissions: Bluetooth "Nearby devices" without location on Android 12+ (location only on 11 and older, which
    need it to scan), the text-to-speech engine, nothing else
  - no backup or phone-to-phone copy of the app's data: the earlier checks stay on this phone
  - icons and splash screen from app/img/icon-512.png, on the app's background colour (dark in dark mode)
  - version: versionCode from RESPIRAI_VERSION_CODE (the GitHub run number), so every build can go to Google Play
  - signing for Google Play when RESPIRAI_KEYSTORE is set (see README.md); otherwise a debug build only
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ANDROID = HERE / "android"
MAIN = ANDROID / "app" / "src" / "main"
RES = MAIN / "res"
ICON = HERE.parent / "app" / "img" / "icon-512.png"
BG_LIGHT, BG_DARK = "#f3f6f9", "#0b1620"   # app/style.css --bg, light and dark


def edit(path, pairs):
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if isinstance(old, re.Pattern):
            text, n = old.subn(new, text, count=1)
        else:
            n = text.count(old)
            text = text.replace(old, new, 1)
        assert n == 1, f"{path.name}: expected once: {old}"
    path.write_text(text, encoding="utf-8")


def manifest():
    edit(MAIN / "AndroidManifest.xml", [
        ('<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
         '<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n    xmlns:tools="http://schemas.android.com/tools">'),
        ('android:allowBackup="true"',
         'android:allowBackup="false"\n        android:fullBackupContent="false"\n        android:dataExtractionRules="@xml/data_extraction_rules"'),
        ('<uses-permission android:name="android.permission.INTERNET" />',
         '<uses-permission android:name="android.permission.INTERNET" />\n'
         '    <!-- Bluetooth (the plugin adds BLUETOOTH_CONNECT): scanning never used for location; location only where\n'
         '         Android 11 and older need it to scan -->\n'
         '    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" tools:targetApi="s" />\n'
         '    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" android:maxSdkVersion="30" />\n'
         '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="30" />\n'
         '    <!-- Spoken instructions: the phone\'s text-to-speech engine -->\n'
         '    <queries>\n'
         '        <intent>\n'
         '            <action android:name="android.intent.action.TTS_SERVICE" />\n'
         '        </intent>\n'
         '    </queries>'),
    ])
    (RES / "xml" / "data_extraction_rules.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!-- Nothing leaves the phone: no cloud backup, no copy to a new phone. -->\n<data-extraction-rules>\n'
        + "".join(f'    <{part}>\n' + "".join(f'        <exclude domain="{d}" path="." />\n' for d in ["root", "file", "database", "sharedpref", "external"])
                  + f'    </{part}>\n' for part in ["cloud-backup", "device-transfer"])
        + "</data-extraction-rules>\n", encoding="utf-8")


def gradle():
    edit(ANDROID / "app" / "build.gradle", [
        (re.compile(r"versionCode \d+"), 'versionCode Integer.parseInt(System.getenv("RESPIRAI_VERSION_CODE") ?: "1")'),
        (re.compile(r'versionName "[^"]*"'), 'versionName "0.1." + (System.getenv("RESPIRAI_VERSION_CODE") ?: "1")'),
        ("    buildTypes {",
         "    signingConfigs {\n"
         "        release {   // the upload key for Google Play, from GitHub secrets (README.md); never in the repository\n"
         '            if (System.getenv("RESPIRAI_KEYSTORE")) {\n'
         '                storeFile file(System.getenv("RESPIRAI_KEYSTORE"))\n'
         '                storePassword System.getenv("RESPIRAI_KEYSTORE_PASSWORD")\n'
         '                keyAlias System.getenv("RESPIRAI_KEY_ALIAS")\n'
         '                keyPassword System.getenv("RESPIRAI_KEY_PASSWORD")\n'
         "            }\n"
         "        }\n"
         "    }\n"
         "    buildTypes {"),
        ("        release {\n            minifyEnabled false",
         '        release {\n            if (System.getenv("RESPIRAI_KEYSTORE")) signingConfig signingConfigs.release\n            minifyEnabled false'),
    ])


def colours_and_splash():
    for folder, bg in [("values", BG_LIGHT), ("values-night", BG_DARK)]:
        (RES / folder).mkdir(exist_ok=True)
        (RES / folder / "respirai_colors.xml").write_text(
            f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="respirai_bg">{bg}</color>\n</resources>\n', encoding="utf-8")
    edit(RES / "values" / "styles.xml", [
        ('    <style name="AppTheme.NoActionBarLaunch" parent="Theme.SplashScreen">\n        <item name="android:background">@drawable/splash</item>',
         '    <style name="AppTheme.NoActionBarLaunch" parent="Theme.SplashScreen">\n        <item name="android:background">@drawable/splash</item>\n'
         '        <item name="windowSplashScreenBackground">@color/respirai_bg</item>'),
    ])
    icon = Image.open(ICON).convert("RGBA")
    for splash in RES.glob("drawable*/splash.png"):   # Android 11 and older: a full-screen picture
        w, h = Image.open(splash).size
        dark = "night" in splash.parent.name
        img = Image.new("RGB", (w, h), BG_DARK if dark else BG_LIGHT)
        side = int(min(w, h) * 0.32)
        badge = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, side - 1, side - 1], fill=255)
        badge.paste(icon.resize((side, side), Image.LANCZOS), (0, 0), mask)
        img.paste(badge, ((w - side) // 2, (h - side) // 2), badge)
        img.save(splash)


def icons():
    icon = Image.open(ICON).convert("RGBA")
    sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for density, px in sizes.items():
        folder = RES / f"mipmap-{density}"
        folder.mkdir(exist_ok=True)
        icon.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher.png")   # Android 7: the square picture
        round_ = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, px - 1, px - 1], fill=255)
        round_.paste(icon.resize((px, px), Image.LANCZOS), (0, 0), mask)
        round_.save(folder / "ic_launcher_round.png")
        # Android 8+: a 108 dp layer, of which a circle of about 66 dp shows; the lungs at 90 % stay inside it.
        layer, inner = px * 9 // 4, int(px * 9 // 4 * 0.9)
        fg = Image.new("RGBA", (layer, layer), "white")
        fg.paste(icon.resize((inner, inner), Image.LANCZOS), ((layer - inner) // 2, (layer - inner) // 2))
        fg.save(folder / "ic_launcher_foreground.png")
        # Android 13+ themed icons: the drawing's lines only, in one colour the phone chooses
        lines = icon.resize((inner, inner), Image.LANCZOS).convert("L").point(lambda v: 255 if v < 225 else 0)
        mono = Image.new("RGBA", (layer, layer), (0, 0, 0, 0))
        mono.paste(Image.new("RGBA", (inner, inner), "white"), ((layer - inner) // 2, (layer - inner) // 2), lines)
        mono.save(folder / "ic_launcher_monochrome.png")
    adaptive = ('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/ic_launcher_background" />\n'
                '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
                '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />\n</adaptive-icon>\n')
    for name in ["ic_launcher.xml", "ic_launcher_round.xml"]:
        (RES / "mipmap-anydpi-v26" / name).write_text(adaptive, encoding="utf-8")
    (RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#FFFFFF</color>\n</resources>\n', encoding="utf-8")


def store_graphics():
    """For the Play Console listing (not in the app): the 512 px icon with alpha, and the 1024 x 500 feature graphic."""
    out = HERE / "store"
    out.mkdir(exist_ok=True)
    Image.open(ICON).convert("RGBA").save(out / "icon-512.png")
    banner = Image.new("RGB", (1024, 500), BG_LIGHT)
    logo = Image.open(HERE.parent / "app" / "img" / "logo.png").convert("RGBA")
    logo = logo.resize((700, int(700 * logo.height / logo.width)), Image.LANCZOS)
    banner.paste(logo, ((1024 - logo.width) // 2, (500 - logo.height) // 2), logo)
    banner.save(out / "feature-graphic-1024x500.png")


if __name__ == "__main__":
    assert (MAIN / "AndroidManifest.xml").exists(), "Run `npx cap add android` first."
    manifest()
    gradle()
    colours_and_splash()
    icons()
    store_graphics()
    print("Android project set up for respirAI")
