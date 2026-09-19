import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models.dart';
import '../profile_store.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.language = 'hi'});

  final String language;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _nameController = TextEditingController();
  final _contactController = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _contactController.dispose();
    super.dispose();
  }

  Future<void> _continue() async {
    if (_saving) return;
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final profile = CitizenProfile(
      name: _nameController.text.trim(),
      contact: _contactController.text.trim(),
      appLanguage: widget.language,
    );
    try {
      await ProfileStore().save(profile);
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/home');
    } on Exception catch (e) {
      setState(() {
        _saving = false;
        _error = 'Save failed: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.record_voice_over_rounded,
                      size: 72, color: scheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    'सहायक  •  Sahayak',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: scheme.primary,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Voice-first grievance assistant\nआवाज़ से शिकायत दर्ज करें',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _nameController,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                      labelText: 'आपका नाम / Your name',
                      prefixIcon: Icon(Icons.person_outline),
                      border: OutlineInputBorder(),
                    ),
                    textInputAction: TextInputAction.next,
                    validator: (v) {
                      final t = v?.trim() ?? '';
                      if (t.isEmpty) return 'Name required (नाम आवश्यक)';
                      if (t.length < 2) return 'Name is too short';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _contactController,
                    keyboardType: TextInputType.phone,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(10),
                    ],
                    decoration: const InputDecoration(
                      labelText: 'मोबाइल नंबर / Mobile number',
                      hintText: '10-digit mobile number',
                      prefixIcon: Icon(Icons.phone_outlined),
                      border: OutlineInputBorder(),
                    ),
                    textInputAction: TextInputAction.done,
                    validator: (v) {
                      final t = v?.trim() ?? '';
                      if (t.isEmpty) return 'Mobile number required';
                      if (t.length != 10) return 'Enter a 10-digit mobile number';
                      return null;
                    },
                    onFieldSubmitted: (_) => _continue(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      _error!,
                      textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.error),
                    ),
                  ],
                  const SizedBox(height: 24),
                  FilledButton.icon(
                    onPressed: _saving ? null : _continue,
                    icon: _saving
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.arrow_forward),
                    label: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      child: Text(_saving ? 'Loading…' : 'जारी रखें  •  Continue'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'This is not a government login. Your name and number are '
                    'saved only on this phone so Sahayak knows what to call '
                    'you and never re-asks for them while you talk.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                  const SizedBox(height: 6),
                  TextButton(
                    onPressed: () => Navigator.of(context)
                        .pushNamedAndRemoveUntil('/language', (_) => false),
                    child: const Text('← Change language'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
