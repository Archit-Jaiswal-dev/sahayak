import 'package:flutter/material.dart';

import '../api_client.dart';
import '../app_languages.dart';
import '../audio_service.dart';

/// First-open language selection: large native-script tiles, a spoken intro in
/// the selected language, and a "Try without signup" demo entry point.
class LanguageScreen extends StatefulWidget {
  const LanguageScreen({super.key});

  @override
  State<LanguageScreen> createState() => _LanguageScreenState();
}

class _LanguageScreenState extends State<LanguageScreen> {
  final AudioService _audio = AudioService();
  final SahayakApi _api = SahayakApi();
  String _selected = 'hi';
  bool _playing = false;

  AppLanguage get _selectedLang =>
      AppLanguage.all.firstWhere((l) => l.code == _selected);

  @override
  void dispose() {
    _audio.dispose();
    super.dispose();
  }

  Future<void> _playIntro() async {
    if (_playing) return;
    setState(() => _playing = true);
    try {
      final lang = _selectedLang;
      // Voice-guided intro in the user's chosen language and voice.
      final audio = await _api.tts(lang.intro, language: lang.code);
      await _audio.play(audio);
    } on Exception {
      // TTS unavailable — text tile still communicates the same message.
    } finally {
      if (mounted) setState(() => _playing = false);
    }
  }

  void _continue() {
    Navigator.of(context).pushNamed('/login');
  }

  void _tryWithoutSignup() {
    Navigator.of(context).pushNamed('/conversation', arguments: {
      'demo': true,
      'language': _selected,
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
              child: Column(
                children: [
                  Icon(Icons.record_voice_over_rounded,
                      size: 56, color: scheme.primary),
                  const SizedBox(height: 8),
                  Text(
                    'सहायक • Sahayak',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: scheme.primary,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Choose your language\nअपनी भाषा चुनें',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: GridView.count(
                padding: const EdgeInsets.all(16),
                crossAxisCount: 2,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: 2.4,
                children: [
                  for (final lang in AppLanguage.all)
                    _languageTile(lang, scheme),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FilledButton.icon(
                    onPressed: _playing ? null : _playIntro,
                    icon: _playing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.volume_up_outlined),
                    label: const Text('Hear a short intro  •  परिचय सुनें'),
                  ),
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: _playing ? null : _continue,
                    icon: const Icon(Icons.arrow_forward),
                    label: const Text('जारी रखें  •  Continue'),
                  ),
                  TextButton(
                    onPressed: _playing ? null : _tryWithoutSignup,
                    child: const Text('Try without signup — record a sample'),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'No signup needed to explore. Your details stay on this '
                    'phone; you are never asked for a CPGRAMS password.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _languageTile(AppLanguage lang, ColorScheme scheme) {
    final selected = lang.code == _selected;
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () => setState(() => _selected = lang.code),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: selected
              ? scheme.primaryContainer
              : scheme.surfaceContainerHighest,
          border: Border.all(
            color: selected ? scheme.primary : Colors.transparent,
            width: 2,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              lang.nativeName,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: selected ? scheme.onPrimaryContainer : null,
                  ),
            ),
            const SizedBox(width: 8),
            Text(
              lang.englishName,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}