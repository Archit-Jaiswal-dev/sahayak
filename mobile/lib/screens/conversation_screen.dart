import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api_client.dart';
import '../app_languages.dart';
import '../app_log.dart';
import '../audio_service.dart';
import '../models.dart';
import '../profile_store.dart';
import 'cpgrams_webview_screen.dart';

enum _MsgRole { assistant, user, system }

class _Message {
  _Message(this.role, this.text);

  final _MsgRole role;
  final String text;
}

class ConversationScreen extends StatefulWidget {
  const ConversationScreen({super.key});

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  final SahayakApi _api = SahayakApi();
  final AudioService _audio = AudioService();
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scroll = ScrollController();

  final List<_Message> _messages = [];
  bool _busy = false;
  bool _recording = false;
  bool _textMode = false;
  bool _speaking = false;
  String _language = 'hi';
  String? _sessionId;
  TurnResult? _lastTurn;
  SessionState? _lastSession;
  bool _demo = false;
  bool _relinking = false;
  int _sttSilences = 0;

  @override
  void initState() {
    super.initState();
    final args =
        (ModalRoute.of(context)?.settings.arguments as Map?) ?? const {};
    _demo = args['demo'] == true;
    _language = (args['language'] as String?) ?? _language;
    _loadLanguageFromProfile();
    _startSession();
  }

  Future<void> _loadLanguageFromProfile() async {
    if (_demo) return;
    try {
      final profile = await ProfileStore().load();
      final lang = profile?.appLanguage;
      if (lang != null && lang.isNotEmpty && lang != _language) {
        _language = lang;
      }
    } on Exception {
      // Non-fatal: keep the default language.
    }
  }

  @override
  void dispose() {
    _audio.dispose();
    _textController.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _startSession() async {
    _setBusy(true);
    appLog.info('conv', 'starting session lang=$_language');
    try {
      final profile = await ProfileStore().load();
      final session = await _api.createSession(
        name: profile?.name,
        contact: profile?.contact,
        language: _language,
      );
      _sessionId = session.sessionId;
      appLog.info('conv', 'session created: ${session.sessionId}');
      _add(_MsgRole.assistant, session.question);
      _speak(session.question);
    } on Exception catch (e) {
      appLog.error('conv', 'session create failed: $e');
      _add(_MsgRole.system, 'Server error: $e');
    } finally {
      _setBusy(false);
    }
  }

  void _restartSession(String language) {
    setState(() {
      _language = language;
      _messages.clear();
      _sessionId = null;
      _lastTurn = null;
      _lastSession = null;
      _textMode = false;
      _recording = false;
    });
    _startSession();
  }

  Future<void> _sendTranscript(String transcript) async {
    if (_busy || transcript.trim().isEmpty) return;
    _setBusy(true);
    appLog.info('conv', 'sending turn: "${transcript.trim()}"');
    _add(_MsgRole.user, transcript.trim());
    try {
      final result = await _api.sendTurn(_sessionId!, transcript.trim());
      _lastTurn = result;
      appLog.info('conv', 'turn ok status=${result.status}');
      _handleTurn(result);
    } on Exception catch (e) {
      appLog.error('conv', 'turn failed: $e');
      _add(_MsgRole.system, 'Error: $e');
    } finally {
      _setBusy(false);
    }
  }

  void _handleTurn(TurnResult result) {
    if (result.isClosed) {
      _add(_MsgRole.assistant, result.message ?? 'Conversation ended.');
      return;
    }
    if (result.isDone) {
      _add(_MsgRole.system, 'Report confirmed. Review the draft below.');
      _loadSessionState();
      final report = result.reportText;
      if (report != null && report.isNotEmpty) {
        _speak(report);
      }
      return;
    }
    if (result.reportText != null) {
      _add(_MsgRole.assistant, result.reportText!);
    }
    final question = result.question;
    if (question != null && question.isNotEmpty) {
      _add(_MsgRole.assistant, question);
      _speak(question);
    }
    if (result.requestGeotag) {
      _add(_MsgRole.system, 'Sahayak needs your location.');
      _captureAndSendLocation();
    }
  }

  Future<void> _speak(String text) async {
    appLog.info('conv', 'tts requested (${text.length} chars)');
    if (!mounted) return;
    setState(() => _speaking = true);
    try {
      final sw = Stopwatch()..start();
      final audio = await _api.tts(text, language: _language);
      sw.stop();
      appLog.info(
        'conv',
        'tts got ${audio.length} bytes',
        durationMs: sw.elapsedMilliseconds,
      );
      await _audio.play(audio);
    } on Exception catch (e) {
      // TTS unavailable (Bhashini not configured) — text already shown.
      appLog.error('conv', 'tts failed: $e');
    } finally {
      if (mounted) setState(() => _speaking = false);
    }
  }

  Future<void> _stopSpeaking() async {
    appLog.info('conv', 'tts stopped by user');
    await _audio.stop();
    if (mounted) setState(() => _speaking = false);
  }

  Future<void> _loadSessionState() async {
    if (_sessionId == null) return;
    try {
      final state = await _api.getSession(_sessionId!);
      if (!mounted) return;
      setState(() => _lastSession = state);
    } on Exception {
      // Non-fatal: draft card still renders from the turn report text.
    }
  }

  /// Geotag flow: the assistant asked whether the citizen is at the location.
  /// We ask for permission, grab the phone's GPS, and reply with a
  /// `[LOCATION: lat, lng]` marker the backend turns into the location slot.
  Future<void> _captureAndSendLocation() async {
    bool granted = false;
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      granted = permission == LocationPermission.whileInUse ||
          permission == LocationPermission.always;
      if (!granted) {
        _add(
          _MsgRole.system,
          'Location permission is off — please type your address instead.',
        );
        return;
      }
      _setBusy(true);
      _add(_MsgRole.system, 'Getting your GPS location…');
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 20),
        ),
      );
      appLog.info(
        'conv',
        'gps -> ${pos.latitude},${pos.longitude}',
      );
      await _sendTranscript(
        '[LOCATION: ${pos.latitude}, ${pos.longitude}]',
      );
    } on Exception catch (e) {
      appLog.error('conv', 'gps failed: $e');
      if (mounted) {
        _add(
          _MsgRole.system,
          'Could not get GPS. Please type your address instead.',
        );
      }
    } finally {
      if (granted) _setBusy(false);
    }
  }

  /// Evidence flow: the assistant asked the citizen to attach a PDF (max 4MB).
  /// Opens the system file picker, uploads the PDF, then replies with a
  /// `[EVIDENCE: <name>]` marker so the backend records it.
  Future<void> _attachEvidence() async {
    if (_sessionId == null) return;
    List<PlatformFile> picked;
    try {
      picked = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf'],
      );
    } on Exception catch (e) {
      appLog.error('conv', 'file picker failed: $e');
      _add(_MsgRole.system, 'Could not open the file picker.');
      return;
    }
    if (picked.isEmpty) return;

    final file = picked.first;
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      _add(_MsgRole.system, 'Could not read that file.');
      return;
    }
    if (bytes.length > 4 * 1024 * 1024) {
      _add(_MsgRole.system, 'File is larger than 4MB. Please pick a smaller PDF.');
      return;
    }
    _setBusy(true);
    _add(_MsgRole.system, 'Uploading your document…');
    try {
      final name = file.name;
      final stored = await _api.uploadEvidence(_sessionId!, bytes, name);
      appLog.info('conv', 'evidence uploaded as $stored');
      await _sendTranscript('[EVIDENCE: $stored]');
    } on Exception catch (e) {
      appLog.error('conv', 'evidence upload failed: $e');
      _add(_MsgRole.system, 'Upload failed: $e');
    } finally {
      _setBusy(false);
    }
  }

  Future<void> _fileGrievance() async {
    if (_demo) {
      // Try-without-signup: no profile, no linking. Surface the path forward
      // without losing the drafted report.
      final go = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Save this complaint  •  शिकायत सहेजें'),
          content: const Text(
            'You explored Sahayak as a guest, so this report was not filed. '
            'Create your local profile (name + mobile) and you can link your '
            'CPGRAMS account and file this exact report.\n\nYour draft is kept.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Not now'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Set up my profile'),
            ),
          ],
        ),
      );
      if (go == true && mounted) {
        Navigator.of(context).pushNamed('/login');
      }
      return;
    }

    // Link-gate: the draft is ready; only ask for the CPGRAMS connection now.
    final profile = await ProfileStore().load();
    final contact = (profile?.contact ?? '').trim();
    final accountKey = contact.isNotEmpty ? 'mobile-$contact' : null;
    if (accountKey == null) {
      _add(_MsgRole.system, 'Please set up your profile to file.');
      if (!mounted) return;
      Navigator.of(context).pushNamed('/login');
      return;
    }
    final linked = await _ensureLinked(accountKey);
    if (!linked) return;

    _setBusy(true);
    _add(_MsgRole.system, 'Filing your complaint…');
    try {
      final regId =
          await _api.fileGrievance(_sessionId!, accountKey: accountKey);
      _add(_MsgRole.system, 'Filed! Registration ID: $regId');
      _speak('आपकी शिकायत दर्ज हो गई है। पंजीकरण संख्या $regId है।');
    } on Exception catch (e) {
      _add(_MsgRole.system, 'Filing error: $e');
    } finally {
      _setBusy(false);
    }
  }

  /// Ensures a live CPGRAMS link exists for this citizen. If not yet linked,
  /// walks the user through the WebView once; if the stored session is stale,
  /// re-links and resumes — the drafted report is never lost.
  Future<bool> _ensureLinked(String accountKey) async {
    // If we already linked during this session and it worked, trust it.
    if (_relinking) return true;
    final profile = await ProfileStore().load();
    if ((profile?.cpgramsLinked ?? false) && accountKey.isNotEmpty) {
      try {
        final status = await _api.cpgramsStatus(accountKey);
        if (status['linked'] == true && status['valid'] != false) {
          return true;
        }
      } on Exception {
        // Fall through to the linking prompt; don't block on a status hiccup.
      }
    }
    if (!mounted) return false;
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Link your CPGRAMS account  •  खाता जोड़ें'),
        content: const Text(
          'To file this complaint under your name, let\u2019s connect your '
          'CPGRAMS account now. This is the real government portal — you will '
          'log in or create an account there directly. Your password goes '
          'straight to them; we never see it.\n\nYour drafted report is safe.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Later'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Link now'),
          ),
        ],
      ),
    );
    if (go != true) return false;
    _relinking = true;
    if (!mounted) return false;
    final linked = await Navigator.of(context)
        .push<bool>(MaterialPageRoute(builder: (_) => const CpgramsWebViewScreen()));
    _relinking = false;
    return linked == true;
  }

  void _add(_MsgRole role, String text) {
    setState(() => _messages.add(_Message(role, text)));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _setBusy(bool busy) => setState(() => _busy = busy);

  @override
  Widget build(BuildContext context) {
    final confirming = _lastTurn?.isConfirming ?? false;
    final done = _lastTurn?.isDone ?? false;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sahayak'),
        centerTitle: true,
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.language),
            tooltip: 'Language',
            onSelected: _restartSession,
            itemBuilder: (_) => [
              for (final lang in AppLanguage.all)
                PopupMenuItem(
                  value: lang.code,
                  child: Text('${lang.nativeName} • ${lang.englishName}'),
                ),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, i) => _bubble(_messages[i]),
            ),
          ),
          if (done)
            _draftReview(scheme)
          else if (confirming)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton(
                          onPressed: _busy ? null : () => _sendTranscript('haan'),
                          child: const Text('Yes — file it'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _busy
                              ? null
                              : () => _sendTranscript('change karne hain'),
                          child: const Text('No — change'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'To fix a detail, just say it, e.g. "पता गांधी चौक है" '
                    'or "change date to 2 days ago"  •  बदलाव के लिए सीधे बोलें',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                ],
              ),
            )
          else if (_lastTurn?.requestEvidence ?? false)
            _evidenceBar(scheme)
          else if (_textMode)
            _textInputBar()
          else
            _voiceBar(scheme),
        ],
      ),
    );
  }

  /// Evidence step: the assistant asked the citizen to attach a PDF (max 4MB).
  /// Offer an attach button plus a "no document" escape so the flow can
  /// proceed without stalling.
  Widget _evidenceBar(ColorScheme scheme) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: _busy ? null : _attachEvidence,
                icon: const Icon(Icons.attach_file),
                label: const Text('Attach PDF (max 4MB)'),
              ),
            ),
            const SizedBox(width: 12),
            OutlinedButton(
              onPressed: _busy ? null : () => _sendTranscript('nahi, koi document nahi hai'),
              child: const Text('No document'),
            ),
          ],
        ),
      ),
    );
  }

  /// Voice-first: a large mic button in the center, a small keyboard toggle
  /// on the right for those who prefer typing.
  Widget _voiceBar(ColorScheme scheme) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
        child: Row(
          children: [
            const SizedBox(width: 48),
            Expanded(
              child: Center(
                child: GestureDetector(
                  onTapDown: _busy ? null : (_) => _startRecording(),
                  onTapUp: _busy ? null : (_) => _stopRecording(),
                  onLongPressEnd: _busy ? null : (_) => _stopRecording(),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: _recording ? 96 : 84,
                    height: _recording ? 96 : 84,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _recording
                          ? scheme.errorContainer
                          : _speaking
                              ? scheme.secondaryContainer
                              : scheme.primary,
                      boxShadow: _recording
                          ? [
                              BoxShadow(
                                color: scheme.error.withValues(alpha: 0.5),
                                blurRadius: 24,
                                spreadRadius: 4,
                              )
                            ]
                          : [
                              BoxShadow(
                                color: scheme.primary.withValues(alpha: 0.35),
                                blurRadius: 16,
                                offset: const Offset(0, 4),
                              )
                            ],
                    ),
                    child: Icon(
                      _recording
                          ? Icons.stop
                          : _speaking
                              ? Icons.stop_circle
                              : Icons.mic,
                      size: _recording ? 48 : 44,
                      color: _speaking && !_recording
                          ? scheme.onSecondaryContainer
                          : scheme.onPrimary,
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(
              width: 48,
              child: IconButton(
                onPressed: _busy ? null : () => setState(() => _textMode = true),
                icon: const Icon(Icons.keyboard_alt_outlined),
                tooltip: 'Type instead',
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _startRecording() async {
    if (_recording || _busy) return;
    // Barge-in: if TTS is speaking, interrupt it so the user can reply
    // without waiting for the prompt to finish.
    if (_speaking) {
      await _stopSpeaking();
    }
    final ok = await _audio.startRecording();
    if (!mounted) return;
    setState(() => _recording = ok);
    if (!ok) {
      final reason = _audio.lastStartError;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            reason != null && reason.isNotEmpty
                ? 'Mic failed: $reason'
                : 'Mic unavailable. Check that the microphone is allowed in '
                    'Settings → Apps → Sahayak → Permissions, then try again.',
          ),
        ),
      );
    }
  }

  Future<void> _stopRecording() async {
    if (!_recording) return;
    final bytes = await _audio.stopRecording();
    if (!mounted) return;
    setState(() => _recording = false);
    if (bytes != null) {
      _add(_MsgRole.system, 'Transcribing…');
      _setBusy(true);
      try {
        final sw = Stopwatch()..start();
        final transcript = await _api.stt(bytes);
        sw.stop();
        appLog.info(
          'conv',
          'stt -> "${transcript.trim()}"',
          durationMs: sw.elapsedMilliseconds,
        );
        if (!mounted) return;
        if (transcript.trim().isEmpty) {
          _sttSilences += 1;
          if (_sttSilences >= 2) {
            _add(
              _MsgRole.system,
              'Still no speech detected. Please speak slowly and clearly, '
              'right up to the microphone, then release the button. '
              '• धीरे और साफ़ बोलें',
            );
            _setBusy(false);
            return;
          }
          _add(
            _MsgRole.system,
            'Could not hear anything. Please repeat slowly. '
            '• धीरे-धीरे दोहराएँ',
          );
          _setBusy(false);
          return;
        }
        _sttSilences = 0;
        // _sendTranscript guards on _busy; release it here so the turn is
        // actually sent (it re-acquires busy for the LLM round-trip).
        _setBusy(false);
        await _sendTranscript(transcript);
      } on Exception catch (e) {
        _add(_MsgRole.system, 'STT error: $e');
        _setBusy(false);
      }
    }
  }

  Widget _textInputBar() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
        child: Row(
          children: [
            IconButton(
              onPressed: _busy ? null : () => setState(() => _textMode = false),
              icon: const Icon(Icons.mic),
              tooltip: 'Voice instead',
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _textController,
                autofocus: true,
                enabled: !_busy,
                decoration: const InputDecoration(
                  hintText: 'Type your message…',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onSubmitted: (t) {
                  _textController.clear();
                  _sendTranscript(t);
                },
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              onPressed: _busy
                  ? null
                  : () {
                      final t = _textController.text;
                      _textController.clear();
                      _sendTranscript(t);
                    },
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bubble(_Message msg) {
    final isAssistant = msg.role == _MsgRole.assistant;
    final isSystem = msg.role == _MsgRole.system;
    final align = isAssistant ? Alignment.centerLeft : Alignment.centerRight;
    final color = isSystem
        ? Colors.amber.shade100
        : isAssistant
            ? Theme.of(context).colorScheme.surfaceContainerHighest
            : Theme.of(context).colorScheme.primaryContainer;
    return Align(
      alignment: align,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: const BoxConstraints(maxWidth: 420),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(msg.text),
      ),
    );
  }

  Widget _draftReview(ColorScheme scheme) {
    final draft = _lastTurn?.reportText ?? 'Report confirmed.';
    final ministry = _lastSession?.slots['ministry'] as String?;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
        child: Card(
          elevation: 0,
          color: scheme.primaryContainer.withValues(alpha: 0.4),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'अंतिम ड्राफ्ट • Final draft',
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
                if (ministry != null && ministry.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    'Route to: $ministry',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: scheme.primary,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ],
                const SizedBox(height: 8),
                Text(draft, style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : _editDetails,
                        icon: const Icon(Icons.edit_outlined),
                        label: const Text('Edit  •  बदलें'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 2,
                      child: _demo
                          ? FilledButton.icon(
                              onPressed: _busy ? null : _fileGrievance,
                              icon: const Icon(Icons.save_alt),
                              label:
                                  const Text('Save  •  शिकायत सहेजें'),
                            )
                          : FilledButton.icon(
                              onPressed: _busy ? null : _fileGrievance,
                              icon: const Icon(Icons.upload_file),
                              label: const Text('Submit to CPGRAMS'),
                            ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () => _shareDraft(),
                    icon: const Icon(Icons.share, size: 18),
                    label: const Text('Share on WhatsApp  •  शेयर करें'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Open WhatsApp with the drafted complaint pre-filled, so the citizen can
  /// keep their own copy or forward it to someone who can help.
  Future<void> _shareDraft() async {
    final draft = _lastTurn?.reportText ?? 'Report confirmed.';
    final ministry = _lastSession?.slots['ministry'] as String?;
    final buf = StringBuffer('Sahayak शिकायत ड्राफ्ट\n');
    if (ministry != null && ministry.isNotEmpty) {
      buf.writeln('Route to: $ministry');
    }
    buf.write('\n$draft');
    final url =
        'https://wa.me/?text=${Uri.encodeComponent(buf.toString())}';
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('WhatsApp not available on this device.')),
      );
    }
  }

  /// Tap-to-edit each field of the drafted report. Editing sends a correction
  /// turn back into the conversation so the backend re-collects that field.
  Future<void> _editDetails() async {
    final slots = _lastSession?.slots ?? {};
    final editable = <String, String>{};
    for (final entry in slots.entries) {
      final v = entry.value;
      if (v is String && v.isNotEmpty) {
        editable[entry.key] = v;
      }
    }
    if (editable.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No editable fields available.')),
      );
      return;
    }
    final controller = TextEditingController();
    String selected = editable.keys.first;
    final corrected = await showDialog<String>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Edit report  •  रिपोर्ट बदलें'),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: selected,
                  decoration: const InputDecoration(labelText: 'Field'),
                  items: [
                    for (final key in editable.keys)
                      DropdownMenuItem(
                        value: key,
                        child: Text(_fieldLabel(key)),
                      ),
                  ],
                  onChanged: (v) {
                    if (v != null) {
                      setDialogState(() {
                        selected = v;
                        controller.text = editable[v] ?? '';
                      });
                    }
                  },
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: controller,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    labelText: 'New value',
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(null),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(
                controller.text.trim(),
              ),
              child: const Text('Apply  •  लागू करें'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
    if (corrected == null || corrected.isEmpty || !mounted) return;
    // Send a correction turn: "category is <new>" so the LLM updates it.
    _sendTranscript('$selected is $corrected. Correct this field.');
  }

  String _fieldLabel(String key) {
    const labels = {
      'category': 'Category  •  श्रेणी',
      'ministry': 'Ministry  •  विभाग',
      'description': 'Description  •  विवरण',
      'location': 'Location  •  स्थान',
      'date': 'Date of issue  •  तारीख',
      'name': 'Name  •  नाम',
      'contact': 'Contact  •  संपर्क',
    };
    return labels[key] ?? key;
  }
}
