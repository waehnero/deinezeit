"""
E-Rechnung (C-5).

Aufbau in drei Schichten, damit ein zweites Format später nicht alles anfasst:

  ``datensatz``   formatneutrale Struktur, aus einem Beleg gebaut
  ``facturx``     serialisiert diese Struktur nach UN/CEFACT CII (ZUGFeRD 2.5 /
                  Factur-X 1.09, Profil EN 16931)
  ``pdf_anhang``  bettet das XML in ein PDF/A-3 ein

Ein späteres ebInterface ist damit ein weiterer Serialisierer neben
``facturx`` — die mühsame Arbeit (Steueraufteilung, Einheitencodes,
Vollständigkeitsprüfung) steckt im Datensatz und wird nicht zweimal gemacht.

**Was diese Schicht nicht leistet:** Sie kann nicht behaupten, dass die
erzeugte Datei konform ist. Das entscheidet ein Validator, nicht der Erzeuger.
Vor dem produktiven Einsatz gehört eine erzeugte Rechnung durch eine externe
Prüfung.
"""
