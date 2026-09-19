import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_log.dart';

/// View the in-app log so failures can be traced to the exact step
/// (session / STT / LLM turn / TTS / filing) that went wrong.
class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key});

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  final AppLog _log = appLog;

  @override
  void initState() {
    super.initState();
    _log.addListener(_onLog);
  }

  @override
  void dispose() {
    _log.removeListener(_onLog);
    super.dispose();
  }

  void _onLog() {
    if (mounted) setState(() {});
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: _log.export()));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Log copied to clipboard')),
    );
  }

  Color _colorFor(LogLevel level) {
    switch (level) {
      case LogLevel.error:
        return Colors.red.shade400;
      case LogLevel.warning:
        return Colors.orange.shade400;
      case LogLevel.debug:
        return Colors.grey.shade500;
      case LogLevel.info:
        return Colors.green.shade400;
    }
  }

  @override
  Widget build(BuildContext context) {
    final entries = _log.entries;
    return Scaffold(
      appBar: AppBar(
        title: const Text('App logs'),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Copy all',
            onPressed: entries.isEmpty ? null : _copy,
            icon: const Icon(Icons.copy_all),
          ),
          IconButton(
            tooltip: 'Clear',
            onPressed: entries.isEmpty
                ? null
                : () {
                    _log.clear();
                    if (mounted) setState(() {});
                  },
            icon: const Icon(Icons.delete_sweep),
          ),
        ],
      ),
      body: entries.isEmpty
          ? const Center(
              child: Text('No log entries yet. Use the app and come back here.'),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: entries.length,
              itemBuilder: (context, i) {
                final e = entries[i];
                return Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: _colorFor(e.level),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: SelectableText(
                          e.line,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                fontFamily: 'monospace',
                                fontSize: 12,
                              ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
    );
  }
}