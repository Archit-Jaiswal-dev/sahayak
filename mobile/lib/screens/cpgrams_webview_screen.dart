import 'dart:async';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api_client.dart';
import '../app_log.dart';
import '../profile_store.dart';

/// Opens the official CPGRAMS citizen portal in an in-app WebView.
///
/// The user logs in / registers directly on the real pgportal.gov.in site —
/// captcha, OTP and password hashing are all handled by CPGRAMS itself. Once
/// the portal lands on an authenticated dashboard, we export the session
/// cookies to the backend (Option A: per-user linked session used for filing).
class CpgramsWebViewScreen extends StatefulWidget {
  const CpgramsWebViewScreen({super.key});

  @override
  State<CpgramsWebViewScreen> createState() => _CpgramsWebViewScreenState();
}

class _CpgramsWebViewScreenState extends State<CpgramsWebViewScreen> {
  static const _signinUrl = 'https://pgportal.gov.in/Signin';
  static const _registrationUrl = 'https://pgportal.gov.in/Registration';

  final SahayakApi _api = SahayakApi();
  late final WebViewController _controller;
  bool _loading = true;
  String _url = '';
  bool _linked = false;
  bool _exportFailed = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) => setState(() => _loading = true),
          onProgress: (progress) {
            if (progress >= 100 && _loading) setState(() => _loading = false);
          },
          onUrlChange: (urlChange) {
            final url = urlChange.url?.toString() ?? '';
            if (url.isEmpty || url == _url) return;
            _url = url;
            _checkLinked();
          },
          onPageFinished: (url) {
            if (_loading) setState(() => _loading = false);
            _url = url;
            _checkLinked();
          },
          onNavigationRequest: (request) => NavigationDecision.navigate,
        ),
      )
      ..loadRequest(Uri.parse(_signinUrl));
    WidgetsBinding.instance.addPostFrameCallback((_) => _showExplanation());
  }

  Future<void> _showExplanation() async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Real CPGRAMS website  •  असली वेबसाइट'),
        content: const Text(
          'You are about to open the official Government of India CPGRAMS '
          'portal. Log in with your existing CPGRAMS account, or tap '
          'Register (पंजीकरण) to create one directly.\n\n'
          'This is the real government website — your password goes straight '
          'to them. After linking, Sahayak may offer to save your login '
          '(encrypted, on the server) so you stay logged in automatically.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Got it  •  ठीक है'),
          ),
        ],
      ),
    );
  }

  Future<String> _accountKey() async {
    final profile = await ProfileStore().load();
    final contact = (profile?.contact ?? '').trim();
    if (contact.isNotEmpty) return 'mobile-$contact';
    final name = (profile?.name ?? '').trim();
    return name.isNotEmpty ? 'name-$name' : 'device-default';
  }

  bool _looksAuthenticated(String url) {
    if (url.contains('/Signin') ||
        url.contains('/Registration') ||
        url.contains('/Error')) {
      return false;
    }
    // Post-login the portal lands on the authenticated citizen area. Match
    // generously (path + the citizen-facing host), since CPGRAMS changes
    // these routes without notice. `/Desk` is the auth-aware landing page the
    // backend verifies against.
    return url.contains('pgportal.gov.in') &&
        (url.contains('/Desk') ||
            url.contains('/Dashboard') ||
            url.contains('/Home/') ||
            url.contains('/UserDashboard') ||
            url.contains('/UserDashBoard') ||
            url.contains('/Complaint') ||
            url.contains('/MyComplaint') ||
            url.contains('/Index'));
  }

  Future<void> _checkLinked() async {
    if (_linked || !_looksAuthenticated(_url)) return;
    await _exportSession();
  }

  Future<void> _exportSession() async {
    if (_linked) return;
    appLog.info('cpgrams', 'detected login; exporting session cookies');
    try {
      final cookies = await WebViewCookieManager()
          .getCookies(domain: Uri.parse('https://pgportal.gov.in'));
      if (cookies.isEmpty) {
        appLog.error('cpgrams', 'no cookies exported from WebView');
        if (!mounted) return;
        setState(() => _exportFailed = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Logged in, but no session cookies were available yet. '
              'Tap "Link account" once the dashboard loads.',
            ),
          ),
        );
        return;
      }
      final list = cookies
          .map((c) => {
                'name': c.name,
                'value': c.value,
                'domain': 'pgportal.gov.in',
                'path': c.path,
              })
          .toList();
      final accountKey = await _accountKey();
      final result = await _api.linkCpgrams(
        accountKey: accountKey,
        cookies: list,
      );
      appLog.info('cpgrams', 'link result: linked=${result['linked']}');
      final profile = await ProfileStore().load();
      if (profile != null) {
        final linked = profile.copyWith(
          cpgramsLinked: true,
          cpgramsLinkedAt: DateTime.now().toIso8601String(),
        );
        await ProfileStore().save(linked);
      }
      // Offer auto-renewal: store the CPGRAMS login (encrypted, server-side)
      // so the app re-logs-in automatically when the session expires.
      await _offerAutoRenewal(accountKey);
      if (!mounted) return;
      setState(() => _linked = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('CPGRAMS account linked  •  खाता जुड़ गया'),
        ),
      );
      // Let callers (e.g. the confirmation gate) know linking succeeded.
      Navigator.of(context).pop(true);
    } on Exception catch (e) {
      appLog.error('cpgrams', 'session export failed: $e');
      if (!mounted) return;
      setState(() => _exportFailed = true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not link account from this session: $e'),
        ),
      );
    }
  }

  void _open(String url) {
    _loading = true;
    _controller.loadRequest(Uri.parse(url));
  }

  /// Ask the citizen (once) whether to store their CPGRAMS login for automatic
  /// session renewal. Skipping is safe: sessions just need a manual re-link.
  Future<void> _offerAutoRenewal(String accountKey) async {
    if (!mounted) return;
    final optIn = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Auto-renew your login?  •  अपने आप जुड़े रहें?'),
        content: const Text(
          'Sahayak can keep you logged in automatically by saving your '
          'CPGRAMS username and password (encrypted, on our server only). '
          'You link once, then never again.\n\n'
          'यह सुविधा आपका उपयोगकर्ता नाम और पासवर्ड एन्क्रिप्ट करके सर्वर पर '
          'सहेजती है, ताकि आपको दोबारा लॉगिन न करना पड़े।',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('No, thanks  •  नहीं'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Save  •  सहेजें'),
          ),
        ],
      ),
    );
    if (optIn != true || !mounted) return;

    final usernameCtrl = TextEditingController();
    final passwordCtrl = TextEditingController();
    final form = GlobalKey<FormState>();
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('CPGRAMS login  •  सीपीग्राम्स लॉगिन'),
        content: Form(
          key: form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Your CPGRAMS login (same details you just used on the portal). '
                'Stored encrypted on the server for auto-renewal.',
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: usernameCtrl,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Username / email  •  उपयोगकर्ता नाम',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: passwordCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Password  •  पासवर्ड',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Skip  •  छोड़ें'),
          ),
          FilledButton(
            onPressed: () {
              if (form.currentState?.validate() ?? false) {
                Navigator.of(ctx).pop(true);
              }
            },
            child: const Text('Save  •  सहेजें'),
          ),
        ],
      ),
    );
    if (saved != true || !mounted) return;

    try {
      await _api.storeCpgramsCredentials(
        accountKey,
        username: usernameCtrl.text.trim(),
        password: passwordCtrl.text.trim(),
      );
      appLog.info('cpgrams', 'credentials stored for auto-renewal');
    } on Exception catch (e) {
      appLog.error('cpgrams', 'credential save failed: $e');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not save credentials: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CPGRAMS  •  सीपीग्राम्स'),
        centerTitle: true,
        actions: [
          if (!_linked && (_looksAuthenticated(_url) || _exportFailed))
            TextButton.icon(
              onPressed: _exportSession,
              icon: const Icon(Icons.link),
              label: const Text('Link account'),
            ),
          PopupMenuButton<String>(
            onSelected: (v) => _open(
              v == 'login' ? _signinUrl : _registrationUrl,
            ),
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'login', child: Text('Login  •  लॉगिन')),
              PopupMenuItem(
                value: 'register',
                child: Text('Register  •  पंजीकरण'),
              ),
            ],
          ),
        ],
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_loading)
            const Positioned.fill(
              child: ColoredBox(
                color: Color(0xEEFFFFFF),
                child: Center(child: CircularProgressIndicator()),
              ),
            ),
        ],
      ),
    );
  }
}