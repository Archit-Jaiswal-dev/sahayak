import 'dart:convert';

class CpgramsProfile {
  CpgramsProfile({
    required this.accountKey,
    this.name = '',
    this.gender = '',
    this.email = '',
    this.mobile = '',
    this.phone = '',
    this.addressLines = const [],
    this.state = '',
    this.district = '',
    this.country = '',
    this.pincode = '',
  });

  final String accountKey;
  final String name;
  final String gender;
  final String email;
  final String mobile;
  final String phone;
  final List<String> addressLines;
  final String state;
  final String district;
  final String country;
  final String pincode;

  String get fullAddress => [
        ...addressLines,
        if (district.isNotEmpty) district,
        if (state.isNotEmpty) state,
        if (pincode.isNotEmpty) pincode,
        if (country.isNotEmpty) country,
      ].join(', ');

  factory CpgramsProfile.fromJson(Map<String, dynamic> json) => CpgramsProfile(
        accountKey: json['account_key'] as String? ?? '',
        name: json['name'] as String? ?? '',
        gender: json['gender'] as String? ?? '',
        email: json['email'] as String? ?? '',
        mobile: json['mobile'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        addressLines: (json['address_lines'] is List
            ? json['address_lines']!.whereType<String>().toList()
            : const <String>[]),
        state: json['state'] as String? ?? '',
        district: json['district'] as String? ?? '',
        country: json['country'] as String? ?? '',
        pincode: json['pincode'] as String? ?? '',
      );

  bool get isEmpty => name.isEmpty &&
      email.isEmpty &&
      mobile.isEmpty &&
      addressLines.isEmpty;
}

class CpgramsRenewResult {
  CpgramsRenewResult({
    required this.renewed,
    this.challenge = '',
    this.token = '',
    this.imageB64 = '',
    this.expiresAt = '',
    this.reason = '',
  });

  final bool renewed;
  final String challenge; // "captcha" | "otp" | ""
  final String token;
  final String imageB64;
  final String expiresAt;
  final String reason;

  factory CpgramsRenewResult.fromJson(Map<String, dynamic> json) =>
      CpgramsRenewResult(
        renewed: json['renewed'] as bool? ?? true,
        challenge: json['challenge'] as String? ?? '',
        token: json['token'] as String? ?? '',
        imageB64: json['image_b64'] as String? ?? '',
        expiresAt: json['expires_at'] as String? ?? '',
        reason: json['reason'] as String? ?? '',
      );
}

class SessionCreated {
  SessionCreated({required this.sessionId, required this.question});

  final String sessionId;
  final String question;

  factory SessionCreated.fromJson(Map<String, dynamic> json) => SessionCreated(
        sessionId: json['session_id'] as String,
        question: json['question'] as String? ?? '',
      );
}

class TurnResult {
  TurnResult({
    required this.status,
    this.question,
    this.filled = const [],
    this.missing = const [],
    this.reportText,
    this.message,
    this.requestGeotag = false,
    this.requestEvidence = false,
  });

  final String status;
  final String? question;
  final List<String> filled;
  final List<String> missing;
  final String? reportText;
  final String? message;
  final bool requestGeotag;
  final bool requestEvidence;

  factory TurnResult.fromJson(Map<String, dynamic> json) => TurnResult(
        status: json['status'] as String,
        question: json['question'] as String?,
        filled: _strList(json['filled']),
        missing: _strList(json['missing']),
        reportText: json['report_text'] as String?,
        message: json['message'] as String?,
        requestGeotag: json['request_geotag'] as bool? ?? false,
        requestEvidence: json['request_evidence'] as bool? ?? false,
      );

  bool get isDone => status == 'done';
  bool get isClosed => status == 'closed';
  bool get isConfirming => status == 'confirming';
  bool get isEvidence => status == 'evidence';
  bool get isAssist => status == 'assist';

  static List<String> _strList(Object? raw) =>
      (raw is List ? raw.whereType<String>().toList() : const <String>[]);
}

class TtsResponse {
  TtsResponse({required this.audioBytes});

  final List<int> audioBytes;

  factory TtsResponse.fromJson(Map<String, dynamic> json, {required String mimeType}) {
    final b64 = json['audio'] as String;
    return TtsResponse(audioBytes: _base64Decode(b64));
  }

  static List<int> _base64Decode(String b64) {
    final normalized = b64.replaceAll('\n', '').replaceAll('\r', '');
    return base64.decode(normalized);
  }
}

class CitizenProfile {
  CitizenProfile({
    required this.name,
    required this.contact,
    this.cpgramsLinked = false,
    this.cpgramsLinkedAt,
    this.appLanguage = 'hi',
    this.dataConsent = true,
  });

  final String name;
  final String contact;
  final bool cpgramsLinked;
  final String? cpgramsLinkedAt;
  final String appLanguage;
  final bool dataConsent;

  Map<String, dynamic> toJson() => {
        'name': name,
        'contact': contact,
        'cpgramsLinked': cpgramsLinked,
        'cpgramsLinkedAt': cpgramsLinkedAt,
        'appLanguage': appLanguage,
        'dataConsent': dataConsent,
      };

  factory CitizenProfile.fromJson(Map<String, dynamic> json) => CitizenProfile(
        name: json['name'] as String? ?? '',
        contact: json['contact'] as String? ?? '',
        cpgramsLinked: json['cpgramsLinked'] as bool? ?? false,
        cpgramsLinkedAt: json['cpgramsLinkedAt'] as String?,
        appLanguage: json['appLanguage'] as String? ?? 'hi',
        dataConsent: json['dataConsent'] as bool? ?? true,
      );

  CitizenProfile copyWith({
    bool? cpgramsLinked,
    String? cpgramsLinkedAt,
    String? appLanguage,
    bool? dataConsent,
  }) =>
      CitizenProfile(
        name: name,
        contact: contact,
        cpgramsLinked: cpgramsLinked ?? this.cpgramsLinked,
        cpgramsLinkedAt: cpgramsLinkedAt ?? this.cpgramsLinkedAt,
        appLanguage: appLanguage ?? this.appLanguage,
        dataConsent: dataConsent ?? this.dataConsent,
      );
}

class SessionState {
  SessionState({
    required this.sessionId,
    required this.status,
    required this.turnCount,
    this.slots = const {},
    this.reportText,
  });

  final String sessionId;
  final String status;
  final int turnCount;
  final Map<String, dynamic> slots;
  final String? reportText;

  factory SessionState.fromJson(Map<String, dynamic> json) => SessionState(
        sessionId: json['session_id'] as String,
        status: json['status'] as String,
        turnCount: json['turn_count'] as int? ?? 0,
        slots: (json['slots'] as Map?)?.cast<String, dynamic>() ?? const {},
        reportText: json['report_text'] as String?,
      );
}

class Grievance {
  Grievance({
    required this.registrationId,
    required this.ministry,
    required this.category,
    required this.description,
    required this.location,
    required this.name,
    required this.contact,
    required this.filedAt,
    required this.deadline,
    required this.slaDays,
    required this.status,
    required this.overdueDays,
    this.appealDraft,
    this.appealFiledAt,
    this.resolvedAt,
  });

  final String registrationId;
  final String ministry;
  final String category;
  final String description;
  final String location;
  final String name;
  final String contact;
  final String filedAt;
  final String deadline;
  final int slaDays;
  final String status;
  final int overdueDays;
  final String? appealDraft;
  final String? appealFiledAt;
  final String? resolvedAt;

  bool get isOverdue => status == 'overdue';
  bool get isEscalated => status == 'escalated';
  bool get isOpen => status == 'open';
  bool get isResolved => status == 'resolved';

  factory Grievance.fromJson(Map<String, dynamic> json) => Grievance(
        registrationId: json['registration_id'] as String,
        ministry: json['ministry'] as String? ?? '',
        category: json['category'] as String? ?? '',
        description: json['description'] as String? ?? '',
        location: json['location'] as String? ?? '',
        name: json['name'] as String? ?? '',
        contact: json['contact'] as String? ?? '',
        filedAt: json['filed_at'] as String? ?? '',
        deadline: json['deadline'] as String? ?? '',
        slaDays: json['sla_days'] as int? ?? 0,
        status: json['status'] as String? ?? '',
        overdueDays: json['overdue_days'] as int? ?? 0,
        appealDraft: json['appeal_draft'] as String?,
        appealFiledAt: json['appeal_filed_at'] as String?,
        resolvedAt: json['resolved_at'] as String?,
      );
}
