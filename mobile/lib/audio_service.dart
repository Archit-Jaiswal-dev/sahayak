import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:record/record.dart';

import 'app_log.dart';

/// Cross-platform voice record + playback.
///
/// Web: recording via MediaRecorder stream, playback via BytesSource.
/// Linux desktop: recording needs PulseAudio; playback needs GStreamer — if
/// either is missing we degrade gracefully (text-only UI still works).
class AudioService {
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();
  final List<int> _chunks = [];
  StreamSubscription<Uint8List>? _subscription;
  StreamSubscription<void>? _completionSubscription;
  Completer<void>? _playingCompleter;
  bool _recording = false;
  bool _playing = false;
  int _sampleRate = 16000;
  String? _lastStartError;

  bool get isRecording => _recording;

  /// True while TTS audio is playing (so the UI can show a stop button).
  bool get isPlaying => _playing;

  String? get lastStartError => _lastStartError;

  Future<bool> hasPermission() async {
    try {
      return await _recorder.hasPermission();
    } catch (_) {
      return false;
    }
  }

  Future<bool> startRecording() async {
    if (_recording) return true;
    appLog.info('audio', 'mic start requested');
    // The record plugin's hasPermission() can report false even when the OS
    // permission IS granted (its activity reference is null until the plugin
    // re-attaches). Don't trust that as a hard blocker — request anyway.
    final granted = await hasPermission();
    appLog.info('audio', 'mic permission granted=$granted');
    _chunks.clear();
    // Some devices throw on a 16k AudioRecord. Fall back to 44.1k (universally
    // supported); the backend resamples anything to 16k mono via PyAV anyway.
    // NOTE: must use pcm16bits — the plugin's `wav` encoder does NOT support
    // stream mode ("Streaming is not supported for encoder 'wav'").
    for (final sampleRate in [16000, 44100]) {
      try {
        _sampleRate = sampleRate;
        final stream = await _recorder.startStream(
          RecordConfig(
            encoder: AudioEncoder.pcm16bits,
            sampleRate: sampleRate,
            numChannels: 1,
          ),
        );
        _subscription = stream.listen(_chunks.addAll);
        _recording = true;
        appLog.info('audio', 'mic recording @ ${sampleRate}Hz pcm16');
        return true;
      } catch (e) {
        // Remember the last error so the UI can show the real cause.
        _lastStartError = e.toString();
        appLog.error('audio', 'startStream @ ${sampleRate}Hz failed: $e');
      }
    }
    // A real SecurityException means the user denied the OS permission.
    if (!granted) {
      appLog.error('audio', 'mic permission denied by OS');
      return false;
    }
    _recording = false;
    return false;
  }

  Future<Uint8List?> stopRecording() async {
    if (!_recording) return null;
    _recording = false;
    try {
      await _subscription?.cancel();
      await _recorder.stop();
    } catch (_) {}
    if (_chunks.isEmpty) {
      appLog.warning('audio', 'recording stopped but captured no audio');
      return null;
    }
    final pcm = Uint8List.fromList(_chunks);
    _chunks.clear();
    // Android stream mode emits raw PCM (16-bit mono) with NO WAV header.
    // Wrap it in a valid WAV container so the backend can decode it.
    final wav = _wrapWav(pcm, _sampleRate);
    appLog.info(
      'audio',
      'mic stopped: ${wav.length} bytes wav '
      '(${(wav.length / _sampleRate / 2).round()}s @ ${_sampleRate}Hz)',
    );
    return wav;
  }

  /// Builds a 44-byte RIFF/WAVE header for 16-bit mono PCM and prepends it.
  Uint8List _wrapWav(Uint8List pcm, int sampleRate) {
    const channels = 1;
    const bitsPerSample = 16;
    final dataSize = pcm.length;
    final byteRate = sampleRate * channels * bitsPerSample ~/ 8;
    final blockAlign = channels * bitsPerSample ~/ 8;

    final header = ByteData(44);
    void writeAscii(int offset, String s) {
      for (var i = 0; i < s.length; i++) {
        header.setUint8(offset + i, s.codeUnitAt(i));
      }
    }

    void writeUint32(int offset, int value) {
      header.setUint32(offset, value, Endian.little);
    }

    void writeUint16(int offset, int value) {
      header.setUint16(offset, value, Endian.little);
    }

    writeAscii(0, 'RIFF');
    writeUint32(4, 36 + dataSize);
    writeAscii(8, 'WAVE');
    writeAscii(12, 'fmt ');
    writeUint32(16, 16);
    writeUint16(20, 1); // PCM
    writeUint16(22, channels);
    writeUint32(24, sampleRate);
    writeUint32(28, byteRate);
    writeUint16(32, blockAlign);
    writeUint16(34, bitsPerSample);
    writeAscii(36, 'data');
    writeUint32(40, dataSize);

    final out = Uint8List(44 + dataSize);
    out.setRange(0, 44, header.buffer.asUint8List());
    out.setRange(44, 44 + dataSize, pcm);
    return out;
  }

  Future<void> play(List<int> bytes) async {
    final sw = Stopwatch()..start();
    // Barge-in: stop any ongoing TTS audio before playing the new one, and
    // complete any in-flight play() so its caller moves on.
    await stop();
    try {
      _playing = true;
      final completer = _playingCompleter = Completer<void>();
      _completionSubscription = _player.onPlayerComplete.listen((_) {
        if (!completer.isCompleted) completer.complete();
      });
      await _player.play(BytesSource(Uint8List.fromList(bytes)));
      sw.stop();
      appLog.info(
        'audio',
        'playing ${bytes.length} bytes tts audio',
        durationMs: sw.elapsedMilliseconds,
      );
      // Hold until playback finishes (or is interrupted by stop()).
      await completer.future;
    } catch (e) {
      // Playback unavailable on this platform — text remains visible.
      appLog.error('audio', 'playback failed: $e');
    } finally {
      await _completionSubscription?.cancel();
      _completionSubscription = null;
      _playing = false;
      _playingCompleter = null;
    }
  }

  /// Interrupts any ongoing TTS playback immediately (barge-in). Safe to call
  /// when nothing is playing.
  Future<void> stop() async {
    if (!_playing) return;
    final completer = _playingCompleter;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
    try {
      await _player.stop();
    } catch (_) {}
  }

  Future<void> dispose() async {
    await _completionSubscription?.cancel();
    await _player.dispose();
    await _recorder.dispose();
  }
}
