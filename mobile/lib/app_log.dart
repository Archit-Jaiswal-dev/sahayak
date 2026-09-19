import 'dart:collection';
import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Severity of a log entry.
enum LogLevel { debug, info, warning, error }

/// A single captured log line.
class LogEntry {
  LogEntry({
    required this.timestamp,
    required this.level,
    required this.source,
    required this.message,
    this.durationMs,
  });

  final DateTime timestamp;
  final LogLevel level;
  final String source;
  final String message;
  final int? durationMs;

  String get levelTag => level.name.toUpperCase().padRight(7);

  String get line {
    final t = timestamp.toIso8601String().split('T').last.split('.').first;
    final dur = durationMs != null ? ' (${durationMs}ms)' : '';
    return '$t  $levelTag [$source] $message$dur';
  }
}

/// In-memory, bounded log buffer so the user can see exactly what the app is
/// doing and where a step failed (STT / LLM / TTS / filing / etc.).
///
/// A single shared instance is exported as [appLog]. Screens listen to it via
/// [addListener] so the logs screen updates live.
class AppLog extends ChangeNotifier {
  AppLog({int maxEntries = 1000}) : _max = maxEntries;

  final int _max;
  final Queue<LogEntry> _entries = Queue<LogEntry>();

  /// Newest-first snapshot for display.
  List<LogEntry> get entries => _entries.toList(growable: false).reversed.toList();

  bool get isEmpty => _entries.isEmpty;

  void clear() {
    _entries.clear();
    notifyListeners();
  }

  void log(
    LogLevel level,
    String source,
    String message, {
    int? durationMs,
  }) {
    if (_entries.length >= _max) {
      _entries.removeFirst();
    }
    _entries.addLast(
      LogEntry(
        timestamp: DateTime.now(),
        level: level,
        source: source,
        message: message,
        durationMs: durationMs,
      ),
    );
    // Also mirror to the debug console (visible via `flutter logs`/adb).
    debugPrint(LogEntry(
      timestamp: DateTime.now(),
      level: level,
      source: source,
      message: message,
      durationMs: durationMs,
    ).line);
    notifyListeners();
  }

  void debug(String source, String message) =>
      log(LogLevel.debug, source, message);

  void info(String source, String message, {int? durationMs}) =>
      log(LogLevel.info, source, message, durationMs: durationMs);

  void warning(String source, String message) =>
      log(LogLevel.warning, source, message);

  void error(String source, String message) =>
      log(LogLevel.error, source, message);

  /// Export all logs as plain text (newest first) for copy/share.
  String export() {
    final buf = StringBuffer('Sahayak app log — ${DateTime.now().toLocal()}\n');
    buf.writeln('─' * 60);
    for (final e in entries) {
      buf.writeln(e.line);
    }
    buf.writeln('─' * 60);
    buf.writeln('${entries.length} entries');
    return buf.toString();
  }

  /// JSON payload used by the optional server push endpoint.
  Map<String, dynamic> toJson() => {
        'app': 'sahayak',
        'generated_at': DateTime.now().toIso8601String(),
        'entries': entries
            .map(
              (e) => {
                'time': e.timestamp.toIso8601String(),
                'level': e.level.name,
                'source': e.source,
                'message': e.message,
                'duration_ms': e.durationMs,
              },
            )
            .toList(),
      };

  String toJsonString() => const JsonEncoder.withIndent('  ').convert(toJson());
}

/// Shared logger instance for the whole app.
final AppLog appLog = AppLog();