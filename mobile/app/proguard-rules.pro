# Keep API model classes so Gson can (de)serialise them after minification
-keep class com.example.stockroom.** { *; }
-keepattributes Signature, *Annotation*
