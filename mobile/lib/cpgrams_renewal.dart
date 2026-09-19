import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../models.dart';

/// Runs the CPGRAMS auto-renewal flow, prompting the citizen to solve a
/// CAPTCHA or enter an OTP in-app when the portal asks for one.
///
/// Returns true when the session was renewed successfully.
Future<bool> runCpgramsRenewal(
  BuildContext context,
  SahayakApi api,
  String accountKey,
) async {
  try {
    final first = await api.renewCpgramsSession(accountKey);
    if (!context.mounted) return false;
    final result = await _walkChallenges(context, api, first);
    if (!context.mounted) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      result
          ? const SnackBar(content: Text('Login renewed  •  लॉगिन नवीनीकृत हुआ'))
          : const SnackBar(content: Text('Renewal not finished  •  नवीनीकरण पूर्ण नहीं')),
    );
    return result;
  } on ApiException catch (e) {
    if (!context.mounted) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Could not renew login: ${e.message}')),
    );
    return false;
  }
}

Future<bool> _walkChallenges(
  BuildContext context,
  SahayakApi api,
  CpgramsRenewResult result,
) async {
  var current = result;
  while (!current.renewed) {
    if (!context.mounted) return false;
    if (current.challenge == 'captcha' && current.token.isNotEmpty) {
      final answer = await _promptCaptcha(context, current.imageB64);
      if (answer == null) return false;
      current = await api.resolveCpgramsRenewal(current.token, answer);
    } else if (current.challenge == 'otp' && current.token.isNotEmpty) {
      final answer = await _promptOtp(context);
      if (answer == null) return false;
      current = await api.resolveCpgramsRenewal(current.token, answer);
    } else {
      return false;
    }
  }
  return current.renewed;
}

Future<String?> _promptCaptcha(BuildContext context, String imageB64) async {
  final controller = TextEditingController();
  Uint8List bytes;
  try {
    bytes = base64Decode(imageB64);
  } catch (_) {
    bytes = Uint8List(0);
  }
  final result = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Verify CAPTCHA  •  कोड दर्ज करें'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'The CPGRAMS portal asked to confirm you are human while '
            'renewing your login. Type the characters shown. '
            '• लॉगिन नवीनीकरण के लिए नीचे दिखे अक्षर दर्ज करें।',
          ),
          const SizedBox(height: 12),
          if (bytes.isNotEmpty)
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.memory(bytes, height: 72, fit: BoxFit.contain),
            ),
          const SizedBox(height: 12),
          TextField(
            controller: controller,
            autofocus: true,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'CAPTCHA  •  कोड',
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Cancel  •  रद्द करें'),
        ),
        FilledButton(
          onPressed: () =>
              Navigator.of(ctx).pop(controller.text.trim()),
          child: const Text('Submit  •  भेजें'),
        ),
      ],
    ),
  );
  return (result == null || result.isEmpty) ? null : result;
}

Future<String?> _promptOtp(BuildContext context) async {
  final controller = TextEditingController();
  final result = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Enter OTP  •  ओटीपी दर्ज करें'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'The CPGRAMS portal sent a one-time password to your phone. '
            'Enter it to finish renewing. '
            '• लॉगिन नवीनीकरण के लिए आपके फ़ोन पर आया ओटीपी दर्ज करें।',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: controller,
            autofocus: true,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'OTP  •  ओटीपी',
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Cancel  •  रद्द करें'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
          child: const Text('Submit  •  भेजें'),
        ),
      ],
    ),
  );
  return (result == null || result.isEmpty) ? null : result;
}
