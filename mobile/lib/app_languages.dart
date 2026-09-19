/// Supported app languages: native-script label, ISO code for the backend,
/// and the Edge TTS voice used for the spoken intro.
class AppLanguage {
  const AppLanguage({
    required this.code,
    required this.nativeName,
    required this.englishName,
    required this.voice,
    required this.intro,
  });

  final String code;
  final String nativeName;
  final String englishName;
  final String voice;
  final String intro;

  static const all = <AppLanguage>[
    AppLanguage(
      code: 'hi',
      nativeName: 'हिन्दी',
      englishName: 'Hindi',
      voice: 'hi-IN-MadhurNeural',
      intro: 'यह ऐप सरकार को आपकी शिकायत सिर्फ बात करके दर्ज करने में मदद करता है।',
    ),
    AppLanguage(
      code: 'en',
      nativeName: 'English',
      englishName: 'English',
      voice: 'en-IN-PrabhatNeural',
      intro: 'This app helps you file complaints to the government just by talking.',
    ),
    AppLanguage(
      code: 'bn',
      nativeName: 'বাংলা',
      englishName: 'Bengali',
      voice: 'bn-IN-TanishaaNeural',
      intro: 'এই অ্যাপটি সরকারের কাছে আপনার অভিযোগ শুধু কথা বলে জমা দিতে সাহায্য করে।',
    ),
    AppLanguage(
      code: 'ta',
      nativeName: 'தமிழ்',
      englishName: 'Tamil',
      voice: 'ta-IN-PallaviNeural',
      intro: 'இந்த ஆப் பேசுவதன் மூலம் அரசாங்கத்திடம் உங்கள் புகாரைப் பதிவு செய்ய உதவுகிறது.',
    ),
    AppLanguage(
      code: 'te',
      nativeName: 'తెలుగు',
      englishName: 'Telugu',
      voice: 'te-IN-ShrutiNeural',
      intro: 'ఈ యాప్ మాట్లాడటం ద్వారా ప్రభుత్వానికి మీ ఫిర్యాదును నమోదు చేయడంలో సహాయపడుతుంది.',
    ),
    AppLanguage(
      code: 'mr',
      nativeName: 'मराठी',
      englishName: 'Marathi',
      voice: 'mr-IN-AarohiNeural',
      intro: 'हे अॅप बोलून सरकारला तुमची तक्रार दाखल करण्यास मदत करते.',
    ),
    AppLanguage(
      code: 'gu',
      nativeName: 'ગુજરાતી',
      englishName: 'Gujarati',
      voice: 'gu-IN-DhwaniNeural',
      intro: 'આ એપ વાત કરીને સરકારને તમારી ફરિયાદ દાખલ કરવામાં મદદ કરે છે.',
    ),
    AppLanguage(
      code: 'kn',
      nativeName: 'ಕನ್ನಡ',
      englishName: 'Kannada',
      voice: 'kn-IN-GaganNeural',
      intro: 'ಈ ಆಪ್ ಮಾತನಾಡುವ ಮೂಲಕ ಸರ್ಕಾರಕ್ಕೆ ನಿಮ್ಮ ದೂರನ್ನು ದಾಖಲಿಸಲು ಸಹಾಯ ಮಾಡುತ್ತದೆ.',
    ),
    AppLanguage(
      code: 'ml',
      nativeName: 'മലയാളം',
      englishName: 'Malayalam',
      voice: 'ml-IN-SobhanaNeural',
      intro: 'ഈ ആപ്പ് സംസാരിച്ചുകൊണ്ട് സർക്കാരിന് നിങ്ങളുടെ പരാതി രജിസ്റ്റർ ചെയ്യാൻ സഹായിക്കുന്നു.',
    ),
    AppLanguage(
      code: 'pa',
      nativeName: 'ਪੰਜਾਬੀ',
      englishName: 'Punjabi',
      voice: 'pa-IN-CharleenNeural',
      intro: 'ਇਹ ਐਪ ਬੋਲ ਕੇ ਸਰਕਾਰ ਨੂੰ ਤੁਹਾਡੀ ਸ਼ਿਕਾਇਤ ਦਰਜ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰਦਾ ਹੈ।',
    ),
  ];
}