import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'profile_store.dart';
import 'screens/consent_screen.dart';
import 'screens/conversation_screen.dart';
import 'screens/cpgrams_webview_screen.dart';
import 'screens/grievances_screen.dart';
import 'screens/home_screen.dart';
import 'screens/language_screen.dart';
import 'screens/login_screen.dart';
import 'screens/logs_screen.dart';
import 'screens/profile_screen.dart';

void main() {
  runApp(const SahayakApp());
}

class SahayakApp extends StatelessWidget {
  const SahayakApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sahayak',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      initialRoute: '/',
      routes: {
        '/': (_) => const _StartupScreen(),
        '/consent': (_) => const ConsentScreen(),
        '/language': (_) => const LanguageScreen(),
        '/login': (_) => const LoginScreen(),
        '/home': (_) => const HomeScreen(),
        '/conversation': (_) => const ConversationScreen(),
        '/cpgrams': (_) => const CpgramsWebViewScreen(),
        '/grievances': (_) => const GrievancesScreen(),
        '/profile': (_) => const ProfileScreen(),
        '/logs': (_) => const LogsScreen(),
      },
    );
  }
}

/// Decides between login (no saved profile) and home on first launch.
class _StartupScreen extends StatefulWidget {
  const _StartupScreen();

  @override
  State<_StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<_StartupScreen> {
  @override
  void initState() {
    super.initState();
    _route();
  }

  Future<void> _route() async {
    final prefs = await SharedPreferences.getInstance();
    final consentGiven = prefs.getBool('sahayak_consent_v1') ?? false;
    final profile = await ProfileStore().load();
    if (!mounted) return;
    // First-open flow: explicit consent → language → signup (or demo). A
    // returning user who has already consented and has a profile goes home.
    final String route;
    if (!consentGiven) {
      route = '/consent';
    } else if (profile == null) {
      route = '/language';
    } else {
      route = '/home';
    }
    Navigator.of(context).pushReplacementNamed(route);
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}
