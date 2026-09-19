import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sahayak_app/main.dart';
import 'package:sahayak_app/screens/login_screen.dart';
import 'package:sahayak_app/screens/home_screen.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('app boots to consent screen when no profile saved',
      (WidgetTester tester) async {
    await tester.pumpWidget(const SahayakApp());
    await tester.pumpAndSettle();
    expect(find.textContaining('privacy first'), findsOneWidget);
    expect(find.textContaining('I agree'), findsOneWidget);
  });

  testWidgets('first-open flow: consent -> language -> login',
      (WidgetTester tester) async {
    await tester.pumpWidget(const SahayakApp());
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('I agree'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Continue'), findsOneWidget);
  });

  testWidgets('login validates empty fields', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.tap(find.textContaining('Continue'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Name required'), findsOneWidget);
  });

  testWidgets('login rejects short mobile number', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.enterText(find.byType(TextFormField).at(0), 'Ram Kumar');
    await tester.enterText(find.byType(TextFormField).at(1), '123');
    await tester.tap(find.textContaining('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Enter a 10-digit mobile number'), findsOneWidget);
  });

  testWidgets('login with valid details proceeds to home',
      (WidgetTester tester) async {
    await tester.pumpWidget(const SahayakApp());
    await tester.pumpAndSettle();
    // First-open: consent → language → login.
    await tester.tap(find.textContaining('I agree'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Continue'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).at(0), 'Ram Kumar');
    await tester.enterText(find.byType(TextFormField).at(1), '9876543210');
    await tester.tap(find.textContaining('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('नई शिकायत • New grievance'), findsOneWidget);
  });

  testWidgets('home screen shows services and profile card',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    expect(find.text('My grievances  •  मेरी शिकायतें'), findsOneWidget);
    expect(find.text('नई शिकायत • New grievance'), findsOneWidget);
    // "Help" is the last ListView item and may be off-screen in the test
    // viewport; scroll until it is visible.
    await tester.scrollUntilVisible(
      find.text('Help  •  सहायता'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Help  •  सहायता'), findsOneWidget);
  });
}
