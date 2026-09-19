import 'package:flutter/material.dart';

import '../api_client.dart';
import '../cpgrams_renewal.dart';
import '../models.dart';
import '../profile_store.dart';

/// Shows the citizen's CPGRAMS account details pulled live from the portal
/// (name, email, mobile, address, state/district/pincode) plus the local
/// Sahayak profile, with a manual refresh.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final SahayakApi _api = SahayakApi();
  final ProfileStore _store = ProfileStore();

  CitizenProfile? _profile;
  CpgramsProfile? _cpgrams;
  bool _loadingCpgrams = false;
  bool _fetchFailed = false;

  @override
  void initState() {
    super.initState();
    _loadLocal();
    _loadCpgrams();
  }

  Future<void> _loadLocal() async {
    final profile = await _store.load();
    if (!mounted) return;
    setState(() => _profile = profile);
  }

  String _accountKey() {
    final contact = (_profile?.contact ?? '').trim();
    if (contact.isNotEmpty) return 'mobile-$contact';
    final name = (_profile?.name ?? '').trim();
    return name.isNotEmpty ? 'name-$name' : 'device-default';
  }

  Future<void> _loadCpgrams() async {
    final linked = _profile?.cpgramsLinked ?? false;
    if (!linked) return;
    setState(() {
      _loadingCpgrams = true;
      _fetchFailed = false;
    });
    try {
      final cpgrams = await _api.fetchCpgramsProfile(_accountKey());
      if (!mounted) return;
      setState(() {
        _cpgrams = cpgrams;
        _loadingCpgrams = false;
      });
    } on Exception {
      if (!mounted) return;
      setState(() {
        _loadingCpgrams = false;
        _fetchFailed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final linked = _profile?.cpgramsLinked ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile  •  प्रोफ़ाइल'),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loadingCpgrams ? null : _loadCpgrams,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _localCard(scheme),
          const SizedBox(height: 16),
          if (linked) ...[
            _sectionTitle(scheme, 'CPGRAMS account  •  सीपीग्राम्स खाता'),
            const SizedBox(height: 8),
            _cpgramsCard(scheme),
          ] else
            _sectionTitle(scheme, 'CPGRAMS account  •  सीपीग्राम्स खाता'),
        ],
      ),
    );
  }

  Widget _localCard(ColorScheme scheme) {
    final p = _profile;
    final name = (p?.name ?? '').trim();
    final contact = (p?.contact ?? '').trim();
    final linked = p?.cpgramsLinked ?? false;
    final language = (p?.appLanguage ?? 'hi').toUpperCase();
    final consent = p?.dataConsent ?? true;
    final linkedAt = p?.cpgramsLinkedAt ?? '';
    return Card(
      elevation: 0,
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 26,
                  backgroundColor: scheme.primaryContainer,
                  child: Icon(Icons.person, color: scheme.primary, size: 28),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name.isNotEmpty
                            ? name
                            : 'Sahayak user  •  सहायक उपयोगकर्ता',
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      if (contact.isNotEmpty)
                        Text(
                          contact,
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: scheme.onSurfaceVariant,
                              ),
                        ),
                    ],
                  ),
                ),
                Icon(
                  linked ? Icons.check_circle : Icons.link_off,
                  color: linked ? scheme.primary : scheme.onSurfaceVariant,
                ),
              ],
            ),
            const Divider(height: 24),
            _row(scheme, Icons.language, 'App language', language),
            _row(
              scheme,
              Icons.privacy_tip_outlined,
              'Share data for pre-filling',
              consent ? 'On  •  चालू' : 'Off  •  बंद',
            ),
            if (linkedAt.isNotEmpty)
              _row(scheme, Icons.event_outlined, 'Linked on',
                  _fmtDate(linkedAt)),
          ],
        ),
      ),
    );
  }

  Widget _cpgramsCard(ColorScheme scheme) {
    if (_loadingCpgrams) {
      return const Card(
        elevation: 0,
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    if (_fetchFailed) {
      return Card(
        elevation: 0,
        color: scheme.errorContainer.withValues(alpha: 0.4),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Icon(Icons.cloud_off, color: scheme.error, size: 36),
              const SizedBox(height: 8),
              const Text(
                'Could not load CPGRAMS account details. '
                'The session may have expired — renew your login. '
                '• विवरण लोड नहीं हुए',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: _loadCpgrams,
                icon: const Icon(Icons.refresh),
                label: const Text('Try again  •  फिर कोशिश करें'),
              ),
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: () async {
                  final renewed = await runCpgramsRenewal(
                    context,
                    _api,
                    _accountKey(),
                  );
                  if (renewed) {
                    await _loadCpgrams();
                  }
                },
                icon: const Icon(Icons.autorenew),
                label: const Text('Renew login  •  लॉगिन नवीनीकरण'),
              ),
            ],
          ),
        ),
      );
    }
    final cp = _cpgrams;
    if (cp == null || cp.isEmpty) {
      return const Card(
        elevation: 0,
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'No account details were returned by the portal. '
            'Some CPGRAMS profiles may not expose editable fields. '
            '• विवरण उपलब्ध नहीं हैं',
          ),
        ),
      );
    }
    return Card(
      elevation: 0,
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _row(scheme, Icons.badge_outlined, 'Name  •  नाम', cp.name),
            if (cp.gender.isNotEmpty)
              _row(scheme, Icons.wc, 'Gender  •  लिंग', cp.gender),
            if (cp.email.isNotEmpty)
              _row(scheme, Icons.email_outlined, 'Email  •  ईमेल', cp.email),
            if (cp.mobile.isNotEmpty)
              _row(
                  scheme, Icons.phone_android, 'Mobile  •  मोबाइल', cp.mobile),
            if (cp.phone.isNotEmpty)
              _row(scheme, Icons.phone_outlined, 'Phone  •  फ़ोन', cp.phone),
            if (cp.fullAddress.isNotEmpty)
              _row(
                  scheme,
                  Icons.location_on_outlined,
                  'Address  •  पता',
                  cp.fullAddress),
            const SizedBox(height: 8),
            Text(
              'Fetched live from your CPGRAMS account  •  '
              'सीपीग्राम्स खाते से लाइव लिया गया',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(ColorScheme scheme, IconData icon, String label, String value) {
    if (value.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: scheme.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                ),
                Text(
                  value,
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(fontWeight: FontWeight.w500),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(ColorScheme scheme, String text) => Text(
        text,
        style: Theme.of(context)
            .textTheme
            .titleMedium
            ?.copyWith(fontWeight: FontWeight.bold, color: scheme.primary),
      );

  String _fmtDate(String iso) {
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    return '${dt.day}/${dt.month}/${dt.year}';
  }
}