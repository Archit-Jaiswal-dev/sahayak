import 'package:flutter/material.dart';

import '../api_client.dart';
import '../cpgrams_renewal.dart';
import '../models.dart';
import '../profile_store.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ProfileStore _store = ProfileStore();
  final SahayakApi _api = SahayakApi();
  CitizenProfile? _profile;
  List<Grievance> _grievances = [];
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    final profile = await _store.load();
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _loaded = true;
    });
    _loadGrievances();
  }

  Future<void> _reloadProfile() async {
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

  Future<void> _loadGrievances() async {
    try {
      final list = await _api.listGrievances();
      if (!mounted) return;
      setState(() => _grievances = list);
    } on Exception {
      // Non-fatal: the home screen works without grievance data.
    }
  }

  Future<void> _logout() async {
    await _store.clear();
    if (!mounted) return;
    Navigator.of(context).pushNamedAndRemoveUntil('/language', (_) => false);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sahayak'),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Account & trust',
            onPressed: () => _openAccount(scheme),
            icon: const Icon(Icons.shield_outlined),
          ),
          IconButton(
            tooltip: 'App logs',
            onPressed: () => Navigator.of(context).pushNamed('/logs'),
            icon: const Icon(Icons.bug_report_outlined),
          ),
          IconButton(
            tooltip: 'Log out',
            onPressed: _logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: !_loaded
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _profileCard(scheme),
                const SizedBox(height: 20),
                if (!(_profile?.cpgramsLinked ?? false))
                  _linkNudge(scheme)
                else
                  _linkedBadge(scheme),
                const SizedBox(height: 20),
                _recordButton(scheme),
                const SizedBox(height: 16),
                if (_grievances.isNotEmpty) ...[
                  _deadlineBanner(scheme),
                  const SizedBox(height: 16),
                ],
                const SizedBox(height: 8),
                Text(
                  'सेवाएँ  •  Services',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 12),
                _serviceTile(
                  scheme,
                  icon: Icons.assignment_outlined,
                  title: 'My grievances  •  मेरी शिकायतें',
                  subtitle: 'Track filed complaints and escalate overdue ones',
                  onTap: () => Navigator.of(context).pushNamed('/grievances'),
                ),
                _serviceTile(
                  scheme,
                  icon: Icons.help_outline,
                  title: 'Help  •  सहायता',
                  subtitle: 'How Sahayak works',
                  onTap: () => _helpDialog(context),
                ),
              ],
            ),
    );
  }

  /// Surface the soonest upcoming SLA deadline (or current overdue status) so
  /// the citizen knows what needs attention without opening the list.
  Widget _deadlineBanner(ColorScheme scheme) {
    final open = _grievances.where((g) => g.isOpen).toList();
    final overdue = _grievances.where((g) => g.isOverdue).toList();

    final DateTime? nextDeadline = () {
      final upcoming = open
          .map((g) => DateTime.tryParse(g.deadline))
          .whereType<DateTime>()
          .where((d) => d.isAfter(DateTime.now()))
          .toList()
        ..sort();
      return upcoming.isNotEmpty ? upcoming.first : null;
    }();

    String title;
    String subtitle;
    IconData icon;
    Color color;
    if (overdue.isNotEmpty) {
      final overdueG = overdue.first;
      title = '${overdue.length} grievance(s) overdue by ${overdueG.overdueDays}d';
      subtitle = 'Action needed  •  कार्रवाई की आवश्यकता';
      icon = Icons.warning_amber_rounded;
      color = scheme.error;
    } else if (nextDeadline != null) {
      final days = nextDeadline.difference(DateTime.now()).inDays;
      title = 'Next deadline: ${_fmtDate(nextDeadline.toIso8601String())}';
      subtitle = '(${days == 0 ? 'today' : '$days day(s) left'}) • '
          'सेवा समय सीमा';
      icon = Icons.event_available;
      color = scheme.primary;
    } else {
      title = 'All grievances on track  •  सब ठीक है';
      subtitle = 'Track progress from My grievances';
      icon = Icons.verified_outlined;
      color = scheme.primary;
    }

    return Card(
      elevation: 0,
      color: color.withValues(alpha: 0.12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(title,
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).pushNamed('/grievances'),
      ),
    );
  }

  String _fmtDate(String iso) {
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  void _openAccount(ColorScheme scheme) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _accountSheet(),
    );
  }

  Widget _accountSheet() {
    final scheme = Theme.of(context).colorScheme;
    final linked = _profile?.cpgramsLinked ?? false;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Account & Trust  •  खाता और भरोसा',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            _sectionTitle('CPGRAMS  •  सीपीग्राम्स'),
            ListTile(
              leading: Icon(
                linked ? Icons.check_circle : Icons.link,
                color: linked ? scheme.primary : scheme.onSurfaceVariant,
              ),
              title: Text(linked ? 'Account linked' : 'Not linked'),
              subtitle: Text(
                linked
                    ? 'Filed under your own CPGRAMS identity'
                    : 'Link to file under your own name',
              ),
              trailing: linked
                  ? TextButton(
                      onPressed: () => _unlink(),
                      child: const Text('Unlink'),
                    )
                  : FilledButton(
                      onPressed: () async {
                        final sheet = Navigator.of(context);
                        await sheet.pushNamed('/cpgrams');
                        await _reloadProfile();
                        if (mounted && (_profile?.cpgramsLinked ?? false)) {
                          sheet.pop();
                        }
                      },
                      child: const Text('Link'),
                    ),
            ),
            if (linked)
              ListTile(
                leading: const Icon(Icons.autorenew),
                title: const Text('Renew login'),
                subtitle: const Text(
                    'Re-login automatically when the session expires'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  final renewed = await runCpgramsRenewal(
                    context,
                    _api,
                    _accountKey(),
                  );
                  if (renewed) {
                    await _reloadProfile();
                  }
                },
              ),
            const Divider(),
            _sectionTitle('Account  •  खाता'),
            ListTile(
              leading: const Icon(Icons.account_circle_outlined),
              title: const Text('View my profile'),
              subtitle: const Text(
                  'CPGRAMS account details, linked status and app data'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.of(context).pop();
                Navigator.of(context).pushNamed('/profile');
              },
            ),
            const Divider(),
            _sectionTitle('Data  •  डेटा'),
            SwitchListTile(
              title: const Text('Share data for grievance pre-filling'),
              subtitle: const Text(
                  'Sahayak may use your name/mobile/location to pre-fill reports. '
                  'Stored only on this phone.'),
              value: _profile?.dataConsent ?? true,
              onChanged: (v) => _setConsent(v),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline),
              title: const Text('Delete my data'),
              subtitle: const Text('Remove everything stored on this phone'),
              onTap: _logout,
            ),
            const SizedBox(height: 8),
            Text(
              'What "linked" means: we store a secure connection to your '
              'CPGRAMS account so we can file and check on complaints for you. '
              'If you opt in, your login is stored encrypted on our server '
              'solely to keep you logged in automatically. You can unlink '
              'anytime.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text(
          text,
          style: Theme.of(context)
              .textTheme
              .titleSmall
              ?.copyWith(color: Theme.of(context).colorScheme.primary),
        ),
      );

  Future<void> _setConsent(bool value) async {
    final p = _profile;
    if (p == null) return;
    final updated = p.copyWith(dataConsent: value);
    await _store.save(updated);
    if (mounted) setState(() => _profile = updated);
  }

  Future<void> _unlink() async {
    final p = _profile;
    if (p == null) return;
    final contact = p.contact.trim();
    final accountKey = contact.isNotEmpty ? 'mobile-$contact' : null;
    if (accountKey != null) {
      try {
        await SahayakApi().unlinkCpgrams(accountKey);
      } on Exception {
        // Local unlink still stands even if the backend call fails.
      }
    }
    final updated = p.copyWith(cpgramsLinked: false, cpgramsLinkedAt: null);
    await _store.save(updated);
    if (!mounted) return;
    setState(() => _profile = updated);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('CPGRAMS account unlinked  •  खाता हटाया गया'),
      ),
    );
  }

  Widget _linkedBadge(ColorScheme scheme) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.primaryContainer.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(Icons.check_circle, color: scheme.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'CPGRAMS linked — complaints are filed under your own account  '
              '•  खाता जुड़ा हुआ है',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }

  Widget _linkNudge(ColorScheme scheme) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => Navigator.of(context).pushNamed('/cpgrams'),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: scheme.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Link your CPGRAMS account to file complaints under your own '
                'name  •  अपने नाम से शिकायत दर्ज करने के लिए खाता जोड़ें',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }

  Widget _recordButton(ColorScheme scheme) {
    return Center(
      child: Column(
        children: [
          GestureDetector(
            onTap: () => Navigator.of(context).pushNamed('/conversation'),
            child: Container(
              width: 148,
              height: 148,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [scheme.primary, scheme.primaryContainer],
                ),
                boxShadow: [
                  BoxShadow(
                    color: scheme.primary.withValues(alpha: 0.4),
                    blurRadius: 28,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: const Icon(
                Icons.mic_rounded,
                size: 72,
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            'नई शिकायत • New grievance',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            'Tap and talk — Sahayak files it for you',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }

  Widget _profileCard(ColorScheme scheme) {
    final name = _profile?.name ?? '—';
    final contact = _profile?.contact ?? '—';
    return Card(
      elevation: 0,
      color: scheme.primaryContainer.withValues(alpha: 0.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).pushNamed('/profile'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              CircleAvatar(
                radius: 26,
                backgroundColor: scheme.primary,
                child: Icon(Icons.person, color: scheme.onPrimary, size: 30),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      contact,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                    ),
                  if ((_profile?.cpgramsLinked ?? false)) ...[
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Icon(Icons.check_circle,
                            size: 14, color: scheme.primary),
                        const SizedBox(width: 4),
                        Text(
                          'CPGRAMS linked  •  खाता जुड़ा',
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(
                                color: scheme.primary,
                                fontWeight: FontWeight.w600,
                              ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        ),
      ),
    );
  }

  Widget _serviceTile(
    ColorScheme scheme, {
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ListTile(
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: CircleAvatar(
          backgroundColor: scheme.secondaryContainer,
          child: Icon(icon, color: scheme.onSecondaryContainer),
        ),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }

  void _helpDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('How Sahayak works'),
        content: const Text(
          '1. Tap the big button and describe your complaint in your language — '
          'by voice or by typing.\n\n'
          '2. Sahayak asks one question at a time until the report is complete.\n\n'
          '3. Review the final report and confirm it.\n\n'
          '4. File it to CPGRAMS under your own linked account.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}