import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// First-open explicit consent. Shown before anything is recorded so the
/// citizen knows, in plain language, how their voice and data are used.
class ConsentScreen extends StatefulWidget {
  const ConsentScreen({super.key});

  @override
  State<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends State<ConsentScreen> {
  static const _consentKey = 'sahayak_consent_v1';
  bool _saving = false;

  Future<void> _accept() async {
    if (_saving) return;
    setState(() => _saving = true);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_consentKey, true);
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed('/language');
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.verified_user_outlined,
                    size: 72, color: scheme.primary),
                const SizedBox(height: 16),
                Text(
                  'Your privacy first  •  गोपनीयता',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: scheme.primary,
                      ),
                ),
                const SizedBox(height: 20),
                _fact(scheme, Icons.mic, 'Your voice is transcribed to text'),
                _fact(
                    scheme,
                    Icons.lock_outline,
                    'Transcripts are used only to draft and file your complaint'),
                _fact(
                    scheme,
                    Icons.phone_iphone,
                    'Your name and number stay on this phone — we never see your '
                    'password'),
                _fact(
                    scheme,
                    Icons.file_upload_outlined,
                    'Filed on the official CPGRAMS portal under your own account'),
                _fact(
                    scheme,
                    Icons.delete_outline,
                    'You can delete all stored data anytime'),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _saving ? null : _accept,
                  icon: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check),
                  label: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    child: Text(_saving ? 'Loading…' : 'मैं सहमत हूँ  •  I agree'),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'You can revoke this at any time from Account & Trust on the '
                  'home screen.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _fact(ColorScheme scheme, IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 22, color: scheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}