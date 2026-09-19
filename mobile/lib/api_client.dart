import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'app_log.dart';
import 'models.dart';

const String apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://localhost:8000',
);

class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class SahayakApi {
  final String _base;
  final http.Client _client;

  SahayakApi({String? base, http.Client? client})
      : _base = base ?? apiBase,
        _client = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$_base$path');

  /// Times a request and records method/path/status/duration in the app log.
  /// The body must already be encoded (raw bytes for the network call).
  Future<http.Response> _logged(
    String method,
    String path,
    Future<http.Response> Function() run,
  ) async {
    final sw = Stopwatch()..start();
    try {
      final resp = await run();
      sw.stop();
      appLog.info(
        'api',
        '$method $path -> ${resp.statusCode}',
        durationMs: sw.elapsedMilliseconds,
      );
      return resp;
    } catch (e) {
      sw.stop();
      appLog.error(
        'api',
        '$method $path failed after ${sw.elapsedMilliseconds}ms: $e',
      );
      rethrow;
    }
  }

  Future<http.Response> _post(String path, Map<String, dynamic> body) {
    return _logged('POST', path, () => _client.post(
          _uri(path),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        ));
  }

  Future<http.Response> _get(String path) {
    return _logged('GET', path, () => _client.get(_uri(path)));
  }

  Future<SessionCreated> createSession({
    String? name,
    String? contact,
    String language = 'hi',
  }) async {
    final resp = await _post('/v1/sessions', {
      if (name != null && name.isNotEmpty) 'name': name,
      if (contact != null && contact.isNotEmpty) 'contact': contact,
      'language': language,
    });
    return SessionCreated.fromJson(_json(resp));
  }

  Future<TurnResult> sendTurn(String sessionId, String transcript) async {
    final resp = await _post('/v1/sessions/$sessionId/turn', {
      'transcript': transcript,
    });
    return TurnResult.fromJson(_json(resp));
  }

  Future<SessionState> getSession(String sessionId) async {
    final resp = await _get('/v1/sessions/$sessionId');
    return SessionState.fromJson(_json(resp));
  }

  Future<String> stt(Uint8List audioBytes) async {
    final request = http.MultipartRequest('POST', _uri('/v1/audio/stt'))
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          audioBytes,
          filename: 'grievance.wav',
          contentType: MediaType('audio', 'wav'),
        ),
      );
    final sw = Stopwatch()..start();
    final streamed = await _client.send(request);
    final resp = await http.Response.fromStream(streamed);
    sw.stop();
    appLog.info(
      'api',
      'POST /v1/audio/stt -> ${resp.statusCode} (${(audioBytes.length / 1024).round()} KB)',
      durationMs: sw.elapsedMilliseconds,
    );
    final data = _json(resp);
    return data['transcript'] as String? ?? '';
  }

  /// Uploads a supporting PDF (max 4MB) for a session. Returns the stored
  /// filename that the caller should echo back as a `[EVIDENCE: <name>]`
  /// conversation turn so the assistant records it.
  Future<String> uploadEvidence(String sessionId, Uint8List bytes, String filename) async {
    final request = http.MultipartRequest(
      'POST',
      _uri('/v1/sessions/$sessionId/evidence'),
    )
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          bytes,
          filename: filename,
          contentType: MediaType('application', 'pdf'),
        ),
      );
    final sw = Stopwatch()..start();
    final streamed = await _client.send(request);
    final resp = await http.Response.fromStream(streamed);
    sw.stop();
    appLog.info(
      'api',
      'POST /v1/sessions/$sessionId/evidence -> ${resp.statusCode}',
      durationMs: sw.elapsedMilliseconds,
    );
    final data = _json(resp);
    return data['filename'] as String;
  }

  Future<List<int>> tts(String text, {String? language}) async {
    final resp = await _post('/v1/audio/tts', {
      'text': text,
      if (language != null && language.isNotEmpty) 'language': language,
    });
    final data = _json(resp);
    return TtsResponse.fromJson(data, mimeType: data['mime_type'] as String? ?? '')
        .audioBytes;
  }

  Future<String> fileGrievance(String sessionId, {String? accountKey}) async {
    final resp = await _post('/v1/filing/file', {
      'session_id': sessionId,
      if (accountKey != null && accountKey.isNotEmpty) 'account_key': accountKey,
    });
    final data = _json(resp);
    return data['registration_id'] as String;
  }

  Future<Map<String, dynamic>> linkCpgrams({
    required String accountKey,
    required List<Map<String, String>> cookies,
  }) async {
    final resp = await _post('/v1/cpgrams/link', {
      'account_key': accountKey,
      'cookies': cookies,
    });
    return _json(resp);
  }

  Future<Map<String, dynamic>> cpgramsStatus(String accountKey) async {
    final resp = await _get('/v1/cpgrams/status?account_key=$accountKey');
    return _json(resp);
  }

  Future<Map<String, dynamic>> storeCpgramsCredentials(
    String accountKey, {
    required String username,
    required String password,
  }) async {
    final resp = await _post('/v1/cpgrams/credentials', {
      'account_key': accountKey,
      'username': username,
      'password': password,
    });
    return _json(resp);
  }

  Future<CpgramsRenewResult> renewCpgramsSession(String accountKey) async {
    final resp = await _post('/v1/cpgrams/renew', {
      'account_key': accountKey,
    });
    return CpgramsRenewResult.fromJson(_json(resp));
  }

  Future<CpgramsRenewResult> resolveCpgramsRenewal(
    String token,
    String answer,
  ) async {
    final resp = await _post('/v1/cpgrams/renew/resolve', {
      'token': token,
      'answer': answer,
    });
    return CpgramsRenewResult.fromJson(_json(resp));
  }

  Future<CpgramsProfile> fetchCpgramsProfile(String accountKey) async {
    final resp = await _get('/v1/cpgrams/profile?account_key=$accountKey');
    return CpgramsProfile.fromJson(_json(resp));
  }

  Future<Map<String, dynamic>> unlinkCpgrams(String accountKey) async {
    final resp = await _post('/v1/cpgrams/unlink', {'account_key': accountKey});
    return _json(resp);
  }

  Future<List<Grievance>> listGrievances() async {
    final resp = await _get('/v1/watchdog/grievances');
    final data = jsonDecode(resp.body) as List;
    return data
        .whereType<Map<String, dynamic>>()
        .map(Grievance.fromJson)
        .toList();
  }

  Future<Grievance> escalateGrievance(String registrationId) async {
    final resp = await _logged(
      'POST',
      '/v1/watchdog/grievances/$registrationId/escalate',
      () => _client.post(_uri('/v1/watchdog/grievances/$registrationId/escalate')),
    );
    return Grievance.fromJson(_json(resp));
  }

  Future<Grievance> resolveGrievance(String registrationId) async {
    final resp = await _logged(
      'POST',
      '/v1/watchdog/grievances/$registrationId/resolve',
      () => _client.post(_uri('/v1/watchdog/grievances/$registrationId/resolve')),
    );
    return Grievance.fromJson(_json(resp));
  }

  Map<String, dynamic> _json(http.Response resp) {
    if (resp.statusCode >= 400) {
      String detail = resp.body;
      try {
        final decoded = jsonDecode(resp.body);
        detail = (decoded is Map && decoded['detail'] is String)
            ? decoded['detail'] as String
            : resp.body;
      } catch (_) {}
      throw ApiException('HTTP ${resp.statusCode}: $detail');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }
}
