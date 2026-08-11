"""
Das XML in ein PDF/A-3 einbetten (hybride Rechnung).

Eine ZUGFeRD-Rechnung ist ein ganz gewöhnliches PDF, in dem eine XML-Datei
steckt. Der Mensch sieht weiter den Beleg, die Software liest das XML. Genau
deshalb ist das Format für den Einstieg gutmütig: Kein Empfänger muss etwas
umstellen.

Drei Dinge müssen dafür zusammenkommen, und WeasyPrint 62.3 liefert nur das
erste von selbst:

1. **PDF/A-3b** — kann WeasyPrint über ``pdf_variant``.
2. **Die eingebettete Datei muss als zugehörig gekennzeichnet sein** —
   ``AFRelationship`` am Dateieintrag und eine ``/AF``-Liste im Katalog.
   WeasyPrint schreibt zwar Anhänge, aber ohne diese Kennzeichnung; ein
   Empfänger fände die Datei dann nicht als Rechnungsdaten, sondern
   bestenfalls als beliebige Beilage.
3. **Das XMP muss das Factur-X-Erweiterungsschema tragen** — daran erkennt
   die Gegenseite überhaupt erst, dass und in welchem Profil hier eine
   E-Rechnung steckt.

Punkt 2 und 3 erledigt der ``finisher``-Rückruf von WeasyPrint: Er bekommt den
fertigen PDF-Baum, bevor er geschrieben wird. Damit kommen wir ohne zusätzliche
Bibliothek aus — ``pydyf`` ist ohnehin schon dabei.

Der Anhang wird hier bewusst **selbst gebaut** statt über WeasyPrints
``attachments``-Parameter: Dessen Dateieintrag lässt sich nachträglich nicht
zuverlässig wiederfinden, und geraten wird hier nichts.
"""
from datetime import datetime, timezone

import pydyf


# Kennzeichnung der Beziehung zwischen PDF und eingebetteter Datei.
# ``Data`` sagt: Das sind die Daten zu genau diesem Dokument.
BEZIEHUNG = "/Data"

# Kennung des Factur-X-Erweiterungsschemas im XMP
FX_NAMESPACE = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
FX_PREFIX = "fx"
FX_VERSION = "1.0"
# Konformitätsstufe = das Profil, in dem das XML gebaut wurde
FX_PROFIL = "EN 16931"


def _xmp(dateiname: str, titel: str = "", autor: str = "") -> bytes:
    """
    Das vollständige XMP-Paket.

    Es wird ganz erzeugt und nicht an das von WeasyPrint angehängt: Zwei
    Quellen für dieselben Angaben wären zwei Gelegenheiten, sich zu
    widersprechen. Die PDF/A-3-Kennung (``pdfaid``) muss mit, sonst ist das
    Dokument formal kein PDF/A mehr.
    """
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f'''<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">

  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>

  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{_escape(titel)}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{_escape(autor)}</rdf:li></rdf:Seq></dc:creator>
  </rdf:Description>

  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:CreateDate>{jetzt}</xmp:CreateDate>
   <xmp:ModifyDate>{jetzt}</xmp:ModifyDate>
   <xmp:CreatorTool>DeineZeit</xmp:CreatorTool>
  </rdf:Description>

  <!-- Erweiterungsschema: Ohne diesen Block ist die eingebettete Datei fuer
       einen Empfaenger nur eine Beilage, keine Rechnung. -->
  <rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
     xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
     xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
   <pdfaExtension:schemas>
    <rdf:Bag>
     <rdf:li rdf:parseType="Resource">
      <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
      <pdfaSchema:namespaceURI>{FX_NAMESPACE}</pdfaSchema:namespaceURI>
      <pdfaSchema:prefix>{FX_PREFIX}</pdfaSchema:prefix>
      <pdfaSchema:property>
       <rdf:Seq>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>DocumentFileName</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>Name des eingebetteten XML-Dokuments</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>DocumentType</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>Art des Dokuments</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>Version</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>Version des Standards</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>ConformanceLevel</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>Profil des eingebetteten Datensatzes</pdfaProperty:description>
        </rdf:li>
       </rdf:Seq>
      </pdfaSchema:property>
     </rdf:li>
    </rdf:Bag>
   </pdfaExtension:schemas>
  </rdf:Description>

  <rdf:Description rdf:about="" xmlns:{FX_PREFIX}="{FX_NAMESPACE}">
   <{FX_PREFIX}:DocumentType>INVOICE</{FX_PREFIX}:DocumentType>
   <{FX_PREFIX}:DocumentFileName>{dateiname}</{FX_PREFIX}:DocumentFileName>
   <{FX_PREFIX}:Version>{FX_VERSION}</{FX_PREFIX}:Version>
   <{FX_PREFIX}:ConformanceLevel>{FX_PROFIL}</{FX_PREFIX}:ConformanceLevel>
  </rdf:Description>

 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''
    return xml.encode("utf-8")


def _escape(text: str) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def finisher(xml_bytes: bytes, dateiname: str, titel: str = "",
             autor: str = "", beschreibung: str = "Rechnungsdaten"):
    """
    Gibt einen ``finisher`` für ``write_pdf`` zurück.

    Der Rückruf bekommt das fertige Dokument und den PDF-Baum, kurz bevor
    dieser geschrieben wird — der einzige Zeitpunkt, zu dem sich Katalog und
    Objekte noch ergänzen lassen.
    """
    def _anwenden(_dokument, pdf):
        jetzt = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")

        # 1. Die Datei selbst. Unkomprimiert: Das XML ist klein, und so bleibt
        #    es im PDF auffindbar — was bei der Fehlersuche mehr wert ist als
        #    ein paar Kilobyte.
        datei = pydyf.Stream([xml_bytes], {
            "Type": "/EmbeddedFile",
            "Subtype": "/text#2Fxml",
            "Params": pydyf.Dictionary({
                "ModDate": pydyf.String(jetzt),
                "Size": len(xml_bytes),
            }),
        }, compress=False)
        pdf.add_object(datei)

        # 2. Der Dateieintrag mit der Beziehungsangabe. Ohne AFRelationship
        #    ist das eine beliebige Beilage, keine Rechnung.
        eintrag = pydyf.Dictionary({
            "Type": "/Filespec",
            "F": pydyf.String(dateiname),
            "UF": pydyf.String(dateiname),
            "Desc": pydyf.String(beschreibung),
            "AFRelationship": BEZIEHUNG,
            "EF": pydyf.Dictionary({"F": datei.reference}),
        })
        pdf.add_object(eintrag)

        # 3. Im Katalog anmelden — an zwei Stellen. Der Namensbaum macht die
        #    Datei im Anhänge-Fenster sichtbar, /AF macht sie maschinell
        #    auffindbar. Beides ist nötig.
        namen = pydyf.Dictionary({
            "Names": pydyf.Array([pydyf.String(dateiname), eintrag.reference]),
        })
        pdf.add_object(namen)
        if "Names" not in pdf.catalog:
            pdf.catalog["Names"] = pydyf.Dictionary()
        pdf.catalog["Names"]["EmbeddedFiles"] = namen.reference
        pdf.catalog["AF"] = pydyf.Array([eintrag.reference])

        # 4. XMP ersetzen. WeasyPrint hat bereits eines geschrieben; unseres
        #    enthält dessen Angaben und zusätzlich das Erweiterungsschema.
        metadaten = pydyf.Stream([_xmp(dateiname, titel, autor)], {
            "Type": "/Metadata",
            "Subtype": "/XML",
        }, compress=False)
        pdf.add_object(metadaten)
        pdf.catalog["Metadata"] = metadaten.reference

    return _anwenden
